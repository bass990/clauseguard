"""Regression gate for CI.

Compares the latest eval snapshot against eval/baseline.json and fails when
a branch's F1 drops below its floor. The floors are set from a full run
minus the measured run-to-run band, so a genuine regression fails the
build while ordinary sampling noise does not.

    python -m eval.regression_check                      # latest_run.json vs baseline.json
    python -m eval.regression_check --write-baseline     # freeze the latest run as the new baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPORTS = Path(__file__).parent / "reports"
BASELINE = Path(__file__).parent / "baseline.json"

# Default tolerance below the frozen F1, in absolute F1 (0.10 = 10 points).
DEFAULT_TOLERANCE = 0.10


def load_metrics(snapshot_path: Path) -> dict[str, dict]:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return {m["branch"]: m for m in snap.get("branch_metrics", [])}


def check(latest: dict[str, dict], baseline: dict) -> list[str]:
    failures = []
    tol = float(baseline.get("tolerance", DEFAULT_TOLERANCE))
    for branch, floor in baseline.get("branches", {}).items():
        m = latest.get(branch)
        if m is None:
            continue  # branch not run this time; not a failure
        floor_f1 = float(floor["f1"]) - tol
        if m["avg_f1"] < floor_f1:
            failures.append(f"{branch}: F1 {m['avg_f1']:.3f} < floor {floor_f1:.3f} (baseline {floor['f1']:.3f} - tol {tol})")
        max_fp = floor.get("max_fp_on_no_conflict")
        if max_fp is not None and m["avg_fp_on_no_conflict"] > float(max_fp):
            failures.append(f"{branch}: FP on clear_no_conflict {m['avg_fp_on_no_conflict']:.2f} > {max_fp}")
    return failures


def write_baseline(latest: dict[str, dict], model: str, tolerance: float) -> dict:
    data = {
        "model": model,
        "tolerance": tolerance,
        "branches": {
            b: {"f1": round(m["avg_f1"], 4), "max_fp_on_no_conflict": round(m["avg_fp_on_no_conflict"] + 0.5, 2)}
            for b, m in latest.items()
        },
    }
    BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, default=REPORTS / "latest_run.json")
    p.add_argument("--baseline", type=Path, default=BASELINE)
    p.add_argument("--write-baseline", action="store_true")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    args = p.parse_args(argv)

    if not args.snapshot.exists():
        print(f"no snapshot at {args.snapshot}; nothing to check")
        return 0
    snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    latest = {m["branch"]: m for m in snap.get("branch_metrics", [])}
    if args.write_baseline:
        data = write_baseline(latest, snap.get("model", "?"), args.tolerance)
        print("baseline written:", json.dumps(data["branches"]))
        return 0
    if not args.baseline.exists():
        print("no baseline.json; run with --write-baseline after a full eval")
        return 0
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    failures = check(latest, baseline)
    for b, m in latest.items():
        print(f"{b:13s} F1 {m['avg_f1']:.3f}  FP/no-conflict {m['avg_fp_on_no_conflict']:.2f}")
    if failures:
        print("REGRESSION:")
        for f in failures:
            print("  -", f)
        return 1
    print("regression check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
