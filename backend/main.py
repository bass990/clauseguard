"""FastAPI surface: upload, SSE analysis stream, PDF export, demo replay.

The API does not contain analysis logic; it wraps backend.pipeline.analyze
in a thread and forwards its events as Server-Sent Events. In demo mode
(CLAUSEGUARD_DEMO=1) uploads are disabled and /analyze/demo replays a
recorded trace of the sample contracts, so a public deployment costs
nothing and accepts no real documents.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, Response, StreamingResponse  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import config  # noqa: E402
from backend.report import generate_pdf  # noqa: E402
from backend.telemetry import Trace  # noqa: E402

ROOT = Path(__file__).parent.parent
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DEMO_TRACE = ROOT / "demo" / "sample_trace.json"
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="ClauseGuard API", version="2.0.0")

_origins = [o.strip() for o in os.getenv("CLAUSEGUARD_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_APP_API_KEY = os.getenv("CLAUSEGUARD_API_KEY")
_bearer = HTTPBearer(auto_error=False)


def require_api_key(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    if not _APP_API_KEY:
        return
    if not credentials or credentials.credentials != _APP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# --------------------------------------------------------------- rate limit
_RATE: dict[str, list[float]] = {}
_RATE_LIMIT = int(os.getenv("CLAUSEGUARD_RATE_LIMIT_PER_MIN", "10"))


def rate_limit(request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    window = [t for t in _RATE.get(ip, []) if now - t < 60]
    if len(window) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded; try again in a minute")
    window.append(now)
    _RATE[ip] = window


@app.middleware("http")
async def request_id_header(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/health")
def health():
    return {"status": "ok", "model": config.MODEL, "fast_model": config.MODEL_FAST, "demo": config.DEMO_MODE}


@app.get("/config")
def public_config():
    return {
        "demo": config.DEMO_MODE,
        "demo_recorded_at": _demo_recorded_at(),
        "routing": config.ROUTING_MODE,
        "judge": config.JUDGE_ENABLED,
        "playbook": config.PLAYBOOK_ENABLED,
        "redact": config.REDACT_ENABLED,
        "ocr": config.OCR_ENABLED,
        "model": config.MODEL,
        "governing_law_options": ["", "New York", "Delaware", "California", "Texas", "England and Wales", "Ontario"],
    }


@app.post("/upload")
async def upload_contracts(
    request: Request,
    contract_a: UploadFile = File(...),
    contract_b: UploadFile = File(...),
    _: None = Depends(require_api_key),
):
    if config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Uploads are disabled in demo mode; use /analyze/demo")
    rate_limit(request)
    for upload in (contract_a, contract_b):
        if not (upload.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"{upload.filename} is not a PDF")
        if upload.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=400, detail=f"{upload.filename} is not a valid PDF")
        contents = await upload.read()
        if len(contents) > config.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"{upload.filename} exceeds the 10MB size limit")
        if not contents.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail=f"{upload.filename} does not look like a PDF")
        await upload.seek(0)

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)
    safe_a = Path(contract_a.filename or "a.pdf").name
    safe_b = Path(contract_b.filename or "b.pdf").name
    path_a = session_dir / f"contract_a_{safe_a}"
    path_b = session_dir / f"contract_b_{safe_b}"
    with open(path_a, "wb") as f:
        shutil.copyfileobj(contract_a.file, f)
    with open(path_b, "wb") as f:
        shutil.copyfileobj(contract_b.file, f)
    return {"session_id": session_id, "contract_a_name": safe_a, "contract_b_name": safe_b}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _stream_pipeline(kwargs: dict, cleanup_dir: Optional[Path] = None):
    """Run the sync pipeline in a worker thread and forward its events."""
    from backend.pipeline import analyze  # noqa: PLC0415

    q: queue.Queue = queue.Queue()
    SENTINEL = object()

    def worker():
        try:
            for ev in analyze(**kwargs):
                q.put(ev)
        except Exception as exc:  # last-resort: never leave the client hanging
            q.put({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    try:
        while True:
            ev = await asyncio.to_thread(q.get)
            if ev is SENTINEL:
                break
            kind = ev.pop("event")
            yield _sse(kind, ev)
            if kind in ("complete", "error"):
                break
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def _demo_recorded_at():
    """When the demo trace was recorded, so the UI can label replayed numbers as historical."""
    if not config.DEMO_MODE or not DEMO_TRACE.exists():
        return None
    try:
        return json.loads(DEMO_TRACE.read_text(encoding="utf-8")).get("recorded_at")
    except (OSError, ValueError):
        return None


@app.get("/analyze/demo")
async def analyze_demo():
    """Replay a recorded analysis of the sample contracts (no model calls)."""
    if not DEMO_TRACE.exists():
        raise HTTPException(status_code=404, detail="No demo trace recorded (run `make record-demo`)")
    data = json.loads(DEMO_TRACE.read_text(encoding="utf-8"))
    events = data["events"]

    async def gen():
        for ev in events:
            ev = dict(ev)
            kind = ev.pop("event")
            if kind == "complete":
                ev["demo_recorded_at"] = data.get("recorded_at")
            await asyncio.sleep(0.35 if kind in ("status", "tool", "route") else 0.05)
            yield _sse(kind, ev)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/analyze/{session_id}")
async def analyze_stream(session_id: str, governing_law: Optional[str] = None, route: Optional[str] = None,
                         _: None = Depends(require_api_key)):
    if config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo mode: use /analyze/demo")
    session_dir = UPLOAD_DIR / session_id
    if not session_dir.exists() or ".." in session_id:
        raise HTTPException(status_code=404, detail="Session not found")
    pdfs = list(session_dir.glob("*.pdf"))
    contract_a = next((str(p) for p in pdfs if p.name.startswith("contract_a_")), None)
    contract_b = next((str(p) for p in pdfs if p.name.startswith("contract_b_")), None)
    if not contract_a or not contract_b:
        raise HTTPException(status_code=400, detail="Two PDFs required")
    kwargs = {
        "contract_a_path": contract_a, "contract_b_path": contract_b,
        "governing_law": governing_law or None,
        "routing_mode": route if route in ("auto", "agentic", "single") else config.ROUTING_MODE,
        "trace": Trace(),
    }
    return StreamingResponse(
        _stream_pipeline(kwargs, cleanup_dir=session_dir),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/generate-pdf")
async def generate_pdf_report(report: dict):
    try:
        pdf_bytes = generate_pdf(report)
        return Response(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=clauseguard-redline-brief.pdf"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


# --------------------------------------------------------------- static UI
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
