"""Tracing, cost accounting and the append-only audit log.

One `Trace` per analysis (request_id). Every model call becomes a span with
tokens, cache reads/writes, latency and cost. The trace summary is streamed
to the UI, printed by the CLI, and appended to a hash-chained JSONL audit
log so a record cannot be altered without breaking the chain.

OpenTelemetry is optional: if `opentelemetry-api` is importable and
CLAUSEGUARD_OTEL=1, spans are mirrored to the configured tracer. Nothing
here requires it.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# USD per million tokens. Override with CLAUSEGUARD_PRICING_JSON if rates change.
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-5": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
    "claude-opus-5": {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.50},
}
_FALLBACK = {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30}

_override = os.getenv("CLAUSEGUARD_PRICING_JSON")
if _override:
    try:
        PRICING.update(json.loads(_override))
    except json.JSONDecodeError:
        pass


def price(model: str) -> dict[str, float]:
    for key, val in PRICING.items():
        if model.startswith(key):
            return val
    return _FALLBACK


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    p = price(model)
    return (
        input_tokens * p["input"] + output_tokens * p["output"]
        + cache_write * p["cache_write"] + cache_read * p["cache_read"]
    ) / 1_000_000


@dataclass
class Span:
    name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    duration_s: float = 0.0
    cost_usd: float = 0.0
    ok: bool = True
    note: str = ""


@dataclass
class Trace:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.time)
    spans: list[Span] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    parse_failures: int = 0
    tool_calls: int = 0

    def record_call(self, name: str, model: str, response, duration_s: float, note: str = "") -> Span:
        u = getattr(response, "usage", None)
        span = Span(
            name=name,
            model=model,
            input_tokens=int(getattr(u, "input_tokens", 0) or 0),
            output_tokens=int(getattr(u, "output_tokens", 0) or 0),
            cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            duration_s=duration_s,
            note=note,
        )
        span.cost_usd = cost_usd(model, span.input_tokens, span.output_tokens, span.cache_write_tokens, span.cache_read_tokens)
        self.spans.append(span)
        _otel_span(span, self.request_id)
        return span

    def event(self, kind: str, **data) -> None:
        self.events.append({"t": round(time.time() - self.started_at, 3), "kind": kind, **data})

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens + s.cache_write_tokens + s.cache_read_tokens for s in self.spans)

    def summary(self) -> dict:
        return {
            "request_id": self.request_id,
            "llm_calls": len(self.spans),
            "tool_calls": self.tool_calls,
            "input_tokens": sum(s.input_tokens for s in self.spans),
            "output_tokens": sum(s.output_tokens for s in self.spans),
            "cache_write_tokens": sum(s.cache_write_tokens for s in self.spans),
            "cache_read_tokens": sum(s.cache_read_tokens for s in self.spans),
            "cost_usd": round(sum(s.cost_usd for s in self.spans), 5),
            "llm_latency_s": round(sum(s.duration_s for s in self.spans), 2),
            "wall_time_s": round(time.time() - self.started_at, 2),
            "parse_failures": self.parse_failures,
            "spans": [asdict(s) for s in self.spans],
        }


def _otel_span(span: Span, request_id: str) -> None:
    if os.getenv("CLAUSEGUARD_OTEL", "").lower() not in ("1", "true"):
        return
    try:
        from opentelemetry import trace as ot  # type: ignore

        tracer = ot.get_tracer("clauseguard")
        with tracer.start_as_current_span(span.name) as s:
            s.set_attribute("request_id", request_id)
            for k, v in asdict(span).items():
                if k != "name":
                    s.set_attribute(f"llm.{k}", v)
    except Exception:
        pass


# ---------------------------------------------------------------- audit log

_LOCK = threading.Lock()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return "0" * 64
    last = "0" * 64
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line).get("hash", last)
                except json.JSONDecodeError:
                    continue
    return last


def _record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def append_audit(record: dict, path: Optional[str] = None) -> dict:
    """Append one record to the hash-chained audit log. Returns the stored record."""
    p = Path(path or os.getenv("CLAUSEGUARD_AUDIT_LOG", "logs/audit.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        prev = _last_hash(p)
        rec = dict(record)
        rec["prev_hash"] = prev
        rec["ts"] = time.time()
        rec["hash"] = _record_hash(rec)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    return rec


def verify_audit(path: Optional[str] = None) -> tuple[bool, int, Optional[int]]:
    """Walk the chain. Returns (ok, n_records, first_bad_index)."""
    p = Path(path or os.getenv("CLAUSEGUARD_AUDIT_LOG", "logs/audit.jsonl"))
    if not p.exists():
        return True, 0, None
    prev = "0" * 64
    n = 0
    with p.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("prev_hash") != prev or _record_hash(rec) != rec.get("hash"):
                return False, n, i
            prev = rec["hash"]
            n += 1
    return True, n, None
