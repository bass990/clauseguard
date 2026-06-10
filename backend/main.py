import sys
import os
import json
import uuid
import asyncio
import shutil
import re
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import anthropic

from config import MODEL, MAX_TOKENS, ANTHROPIC_API_KEY, SYSTEM_PROMPT, MAX_FILE_SIZE
from backend.tools import TOOLS, TOOL_MAP
from backend.report import generate_pdf

app = FastAPI(title="ClauseGuard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Anchor upload dir to the project root, not the cwd of wherever uvicorn is launched
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Optional API key guard — set CLAUSEGUARD_API_KEY in .env to enable
_APP_API_KEY = os.getenv("CLAUSEGUARD_API_KEY")
_bearer = HTTPBearer(auto_error=False)

def require_api_key(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    if not _APP_API_KEY:
        return  # Auth disabled — local/dev mode
    if not credentials or credentials.credentials != _APP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.post("/upload")
async def upload_contracts(
    contract_a: UploadFile = File(...),
    contract_b: UploadFile = File(...),
    _: None = Depends(require_api_key)
):
    """Upload two contract PDFs and return their server paths."""
    for upload in (contract_a, contract_b):
        if not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"{upload.filename} is not a PDF")
        if upload.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=400, detail=f"{upload.filename} is not a valid PDF")

        contents = await upload.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename} exceeds the 10MB size limit"
            )
        # Seek back so the file can be read again when saving
        await upload.seek(0)

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)

    path_a = session_dir / f"contract_a_{contract_a.filename}"
    path_b = session_dir / f"contract_b_{contract_b.filename}"

    with open(path_a, "wb") as f:
        shutil.copyfileobj(contract_a.file, f)
    with open(path_b, "wb") as f:
        shutil.copyfileobj(contract_b.file, f)

    return {
        "session_id": session_id,
        "contract_a_path": str(path_a),
        "contract_b_path": str(path_b),
        "contract_a_name": contract_a.filename,
        "contract_b_name": contract_b.filename,
    }


@app.get("/analyze/{session_id}")
async def analyze_stream(session_id: str, _: None = Depends(require_api_key)):
    """
    Stream the agent analysis as Server-Sent Events.
    Client receives progress updates and the final report.
    """
    session_dir = UPLOAD_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    pdfs = list(session_dir.glob("*.pdf"))
    if len(pdfs) < 2:
        raise HTTPException(status_code=400, detail="Two PDFs required")

    contract_a = next((str(p) for p in pdfs if "contract_a" in p.name), None)
    contract_b = next((str(p) for p in pdfs if "contract_b" in p.name), None)

    if not contract_a or not contract_b:
        raise HTTPException(status_code=400, detail="Could not identify contract files")

    async def event_stream():
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        try:
            yield sse("status", {"message": "Starting analysis...", "step": 0, "total": 3})
            await asyncio.sleep(0.1)

            messages = [
                {
                    "role": "user",
                    "content": (
                        f"Analyze these two contracts for conflicts and generate a complete redline brief.\n\n"
                        f"Contract A (our company standard terms): {contract_a}\n"
                        f"Contract B (vendor/supplier terms): {contract_b}\n\n"
                        f"Follow your workflow: extract clauses from both, find conflicts, "
                        f"then generate the final redline brief."
                    )
                }
            ]

            step_map = {
                "extract_clauses":        (1, "Extracting clauses from contracts..."),
                "generate_redline_brief": (2, "Generating redline brief..."),
            }

            redline_report = None
            turn = 0
            max_turns = 20

            while turn < max_turns:
                turn += 1

                try:
                    async with client.messages.stream(
                        model=MODEL,
                        max_tokens=MAX_TOKENS,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS,
                        messages=messages
                    ) as stream:
                        response = await stream.get_final_message()
                except Exception as e:
                    yield sse("error", {"message": str(e)})
                    return

                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    # If generate_redline_brief was never called, try to scrape JSON from
                    # the final text response as a last resort
                    if not redline_report:
                        final_text = ""
                        for block in response.content:
                            if hasattr(block, "text"):
                                final_text = block.text
                        try:
                            json_match = re.search(r'\{.*"conflicts".*\}', final_text, re.DOTALL)
                            if json_match:
                                parsed = json.loads(json_match.group())
                                if "conflicts" in parsed:
                                    redline_report = {"report": parsed}
                        except Exception:
                            pass

                    yield sse("status", {"message": "Analysis complete!", "step": 3, "total": 3})

                    if redline_report:
                        yield sse("complete", redline_report)
                    else:
                        final_text = next(
                            (block.text for block in response.content if hasattr(block, "text")), ""
                        )
                        yield sse("complete", {
                            "report": {
                                "title": "Contract Conflict Analysis",
                                "total_conflicts": 0,
                                "summary": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                                "conflicts": [],
                                "recommendation": final_text or "Analysis complete. No structured conflicts identified.",
                                "raw_analysis": final_text
                            }
                        })
                    return

                if response.stop_reason == "tool_use":
                    tool_results = []

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        tool_name = block.name
                        tool_input = block.input

                        step, msg = step_map.get(tool_name, (turn, f"Running {tool_name}..."))
                        yield sse("status", {"message": msg, "step": step, "total": 3, "tool": tool_name})
                        await asyncio.sleep(0.05)

                        try:
                            result = TOOL_MAP[tool_name](**tool_input)

                            # Capture the redline report as soon as it's produced
                            if tool_name == "generate_redline_brief" and result.get("success"):
                                redline_report = result

                            # Surface truncation warnings to the UI
                            if tool_name == "extract_clauses" and result.get("truncated"):
                                yield sse("status", {
                                    "message": result["truncation_warning"],
                                    "step": step,
                                    "total": 3
                                })

                        except Exception as e:
                            result = {"error": str(e)}
                            yield sse("status", {"message": f"Tool error: {e}", "step": step, "total": 3})

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result)
                        })

                    messages.append({"role": "user", "content": tool_results})

            yield sse("error", {"message": "Analysis timed out. Try with shorter contracts."})

        finally:
            # Always clean up uploaded files — whether analysis succeeded, errored, or client disconnected
            shutil.rmtree(session_dir, ignore_errors=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/generate-pdf")
async def generate_pdf_report(report: dict):
    """
    Accept a report JSON object and return a formatted PDF.
    The frontend sends the report data it already has — no session needed.
    """
    try:
        pdf_bytes = generate_pdf(report)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=clauseguard-redline-brief.pdf"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
