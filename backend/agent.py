"""CLI entry point. Runs the same pipeline the API streams.

    python -m backend.agent sample_contracts/company_standard_terms.pdf sample_contracts/vendor_proposed_terms.pdf
    python -m backend.agent a.pdf b.pdf --law Delaware --route agentic --no-judge --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from backend.pipeline import analyze  # noqa: E402


def run_agent(contract_a_path: str, contract_b_path: str, on_progress=None, **kwargs) -> dict:
    """Backwards-compatible wrapper: returns {success, report|error}."""
    report = None
    for ev in analyze(contract_a_path, contract_b_path, **kwargs):
        if on_progress:
            on_progress(ev)
        elif ev["event"] in ("status", "route", "tool", "judge"):
            print(f"[{ev['event']}] " + (ev.get("message") or ev.get("summary") or ev.get("reason") or json.dumps(ev)))
        if ev["event"] == "complete":
            report = ev["report"]
        if ev["event"] == "error":
            return {"success": False, "error": ev["message"], "report": None}
        if ev["event"] == "trace" and not on_progress:
            print(f"[trace] {ev['llm_calls']} calls, {ev['input_tokens']:,} in / {ev['output_tokens']:,} out, "
                  f"cache read {ev['cache_read_tokens']:,}, ${ev['cost_usd']:.4f}, {ev['wall_time_s']}s")
    return {"success": report is not None, "report": report}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ClauseGuard contract conflict analysis")
    p.add_argument("contract_a")
    p.add_argument("contract_b")
    p.add_argument("--law", default=None, help="Expected governing law, e.g. 'New York'")
    p.add_argument("--route", default=config.ROUTING_MODE, choices=["auto", "agentic", "single"])
    p.add_argument("--no-judge", action="store_true")
    p.add_argument("--no-playbook", action="store_true")
    p.add_argument("--model", default=config.MODEL)
    p.add_argument("--json", default=None, help="Write the report JSON to this path")
    args = p.parse_args(argv)

    result = run_agent(
        args.contract_a, args.contract_b, governing_law=args.law, routing_mode=args.route,
        judge=not args.no_judge, playbook=not args.no_playbook, model=args.model,
    )
    if args.json and result.get("report"):
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result["report"], f, indent=2)
        print(f"report written to {args.json}")
    if not result["success"]:
        print("ERROR:", result.get("error"))
        return 1
    r = result["report"]
    print(f"\n=== {r['total_conflicts']} conflicts ({r['summary']}) via {r['route']} ===")
    for c in r["conflicts"]:
        rv = c.get("resolution_review", {}).get("verdict", "-")
        print(f"[{c['risk']}] {c['topic']}  favor={c['favor']}  ref={c.get('playbook_ref')}  review={rv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
