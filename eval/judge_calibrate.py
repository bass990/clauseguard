"""Measure the resolution judge against hand-labelled verdicts.

    python -m eval.judge_calibrate            # ~12 Haiku calls, a few cents

Prints exact-verdict agreement, a confusion matrix and the "safe-side"
rate (how often the judge is at least as strict as the label), and writes
eval/reports/judge_calibration.json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from backend.judge import judge_conflict  # noqa: E402
from backend.pipeline import make_client  # noqa: E402

CASES = Path(__file__).parent / "judge_calibration.json"
OUT = Path(__file__).parent / "reports" / "judge_calibration.json"
STRICTNESS = {"pass": 0, "flag": 1, "hide": 2}


def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    client = make_client()
    rows = []
    for c in cases:
        review = judge_conflict(dict(c["conflict"], id=1), client, config.MODEL_FAST)
        rows.append({"id": c["id"], "expected": c["expected"], "got": review["verdict"], "reason": review["reason"],
                     "model_verdict": review.get("model_verdict"), "sound": review.get("sound"),
                     "one_sided": review.get("one_sided"), "ambiguous": review.get("ambiguous"),
                     "citation_valid": review.get("citation_valid")})
        print(f"{c['id']}  expected {c['expected']:5s}  got {review['verdict']:5s}  (model said {review.get('model_verdict')}, "
              f"sound={review.get('sound')})  {review['reason'][:70]}")
    exact = sum(r["expected"] == r["got"] for r in rows) / len(rows)
    safe = sum(STRICTNESS[r["got"]] >= STRICTNESS[r["expected"]] for r in rows) / len(rows)
    confusion = Counter((r["expected"], r["got"]) for r in rows)
    print(f"\nexact agreement {exact:.0%}  safe-side (judge at least as strict as label) {safe:.0%}  n={len(rows)}")
    print("confusion (expected -> got):", dict(confusion))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"model": config.MODEL_FAST, "n": len(rows), "exact_agreement": exact,
                               "safe_side_rate": safe, "confusion": {f"{a}->{b}": n for (a, b), n in confusion.items()},
                               "rows": rows}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
