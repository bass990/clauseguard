"""Record a real analysis of the sample contracts as a replayable demo trace.

    python scripts/record_demo.py            # writes demo/sample_trace.json

The public demo (CLAUSEGUARD_DEMO=1) replays this file from /analyze/demo,
so a deployed instance costs nothing per visitor and never receives a
real contract. Re-run after changing prompts, the playbook or the model.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from backend.pipeline import analyze  # noqa: E402


def main() -> int:
    out = ROOT / "demo" / "sample_trace.json"
    out.parent.mkdir(exist_ok=True)
    events = []
    for ev in analyze(
        str(ROOT / "sample_contracts" / "company_standard_terms.pdf"),
        str(ROOT / "sample_contracts" / "vendor_proposed_terms.pdf"),
        audit_log=os.devnull if os.name != "nt" else str(ROOT / "logs" / "demo_audit.jsonl"),
    ):
        events.append(ev)
        print(ev["event"], (ev.get("message") or ev.get("summary") or ev.get("route") or "")[:90])
    if events[-1]["event"] != "complete":
        print("analysis did not complete; trace not written")
        return 1
    out.write_text(json.dumps({
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "model": config.MODEL,
        "fast_model": config.MODEL_FAST,
        "events": events,
    }, indent=1), encoding="utf-8")
    print(f"wrote {out} ({len(events)} events, {events[-1]['report']['total_conflicts']} conflicts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
