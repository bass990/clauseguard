"""Orchestration + report rendering for ClauseGuard eval runs.

run_eval() runs the Cartesian product (scenarios × branches × reps), captures
pipeline errors as ScenarioResult.error rather than crashing the run, and
aggregates costs via instrumentation.aggregate_traces.

render_report() generates a markdown report with:
- Headline A/B finding
- Per-branch metrics tables
- Per-tier breakdown
- A/B lift table per metric family
- Per-scenario detail (errors highlighted)
- Cost / latency totals
- Eval-mode methodology disclosure footer

save_run() writes the report to eval/reports/run_YYYYMMDD_HHMMSS.md and a
JSON snapshot to latest_run.json for re-rendering.

The default eval-small scenario set spans every tier AND includes
adversarial_001 (the prompt-injection scenario, highest-value-per-call
per ChainPilot precedent).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from eval.instrumentation import (
    CallTrace,
    aggregate_traces,
    format_totals,
)
from eval.runners import (
    list_scenarios,
    load_scenario,
    run_full_pipeline,
    run_stripped_pipeline,
)
from eval.schemas import (
    ABLiftResult,
    BranchMetrics,
    ConflictCountRange,
    Scenario,
    ScenarioResult,
)
from eval.scorers import aggregate_branch_metrics, compute_ab_lift


# 5 scenarios chosen to span all 5 tiers and include adversarial_001
# (the prompt-injection scenario, highest-value single test).
DEFAULT_EVAL_SMALL_SCENARIO_IDS: list[str] = [
    "clear_conflict_001",       # Liability cap mismatch
    "clear_no_conflict_001",    # Payment terms — Rule 2
    "ambiguous_001",            # Notice periods 30 vs 35
    "severity_tiering_003",     # Arbitration tier discipline
    "adversarial_001",          # Prompt injection — most important
]


# ---------------------------------------------------------------------------
# run_eval
# ---------------------------------------------------------------------------


def _branch_runner(branch: str):
    if branch == "full":
        return run_full_pipeline
    if branch == "stripped":
        return run_stripped_pipeline
    raise ValueError(f"Unknown branch: {branch}")


def run_eval(
    scenario_ids: list[str],
    branches: list[str],
    n_reps: int,
    scenarios_dir: Path,
    model: str = "claude-sonnet-4-6",
    on_trace=None,
) -> list[ScenarioResult]:
    """Run scenarios × branches × reps. Errors captured per-result."""
    results: list[ScenarioResult] = []
    for scenario_id in scenario_ids:
        path = scenarios_dir / f"{scenario_id}.json"
        if not path.exists():
            results.append(
                ScenarioResult(
                    scenario_id=scenario_id,
                    tier="clear_conflict",  # placeholder; record an error
                    branch="full",  # type: ignore[arg-type]
                    rep=0,
                    error=f"Scenario file not found: {path}",
                )
            )
            continue
        scenario = load_scenario(path)
        for branch in branches:
            runner = _branch_runner(branch)
            for rep in range(n_reps):
                result = runner(
                    scenario=scenario,
                    rep=rep,
                    model=model,
                    on_trace=on_trace,
                )
                results.append(result)
    return results


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_num(x: float) -> str:
    return f"{x:.3f}"


def _headline(lifts: list[ABLiftResult]) -> str:
    """One-paragraph headline framing the A/B finding."""
    f1 = next((lift for lift in lifts if lift.metric == "f1"), None)
    if f1 is None:
        return "_(No F1 lift to summarize.)_"
    lift_pp = f1.lift * 100
    full = _fmt_pct(f1.full_score)
    stripped = _fmt_pct(f1.stripped_score)
    if f1.interpretation == "full_wins":
        verdict = (
            f"**FULL pipeline beats STRIPPED by {lift_pp:+.1f}pp on F1** "
            f"(FULL: {full} vs STRIPPED: {stripped}). The two-tool agentic "
            f"architecture earns its complexity on this eval."
        )
    elif f1.interpretation == "stripped_wins":
        verdict = (
            f"**STRIPPED single-prompt baseline beats FULL pipeline by "
            f"{-lift_pp:+.1f}pp on F1** (FULL: {full} vs STRIPPED: {stripped}). "
            f"The two-tool agentic loop is costing precision/recall — "
            f"investigate per-tier breakdown and per-scenario details before "
            f"shipping any conclusion."
        )
    else:
        verdict = (
            f"**FULL ≈ STRIPPED on F1** ({lift_pp:+.1f}pp difference; "
            f"FULL: {full} vs STRIPPED: {stripped}). The agentic architecture "
            f"is performing the same as a single-prompt baseline — recommend "
            f"reaching for the simpler architecture for production."
        )
    return verdict


def _render_branch_table(metrics: BranchMetrics) -> str:
    return (
        f"### Branch `{metrics.branch}`\n"
        f"_n_scenarios={metrics.n_scenarios}, n_reps={metrics.n_reps}_\n\n"
        f"| Metric | Value |\n"
        f"|---|---|\n"
        f"| Precision | {_fmt_pct(metrics.avg_precision)} |\n"
        f"| Recall | {_fmt_pct(metrics.avg_recall)} |\n"
        f"| F1 | {_fmt_pct(metrics.avg_f1)} |\n"
        f"| Risk strict | {_fmt_pct(metrics.risk_strict_acc)} |\n"
        f"| Risk lenient | {_fmt_pct(metrics.risk_lenient_acc)} |\n"
        f"| Favor strict | {_fmt_pct(metrics.favor_strict_acc)} |\n"
        f"| Favor lenient | {_fmt_pct(metrics.favor_lenient_acc)} |\n"
        f"| Avg FP per `clear_no_conflict` scenario | {_fmt_num(metrics.avg_fp_on_no_conflict)} |\n"
        f"| Count MAE | {_fmt_num(metrics.count_mae)} |\n"
    )


def _render_per_tier_breakdown(
    full: BranchMetrics, stripped: BranchMetrics
) -> str:
    tiers = sorted(set(full.per_tier.keys()) | set(stripped.per_tier.keys()))
    lines = [
        "### Per-tier F1 breakdown",
        "",
        "| Tier | FULL F1 | STRIPPED F1 | Lift (pp) |",
        "|---|---|---|---|",
    ]
    for tier in tiers:
        f_f1 = full.per_tier.get(tier, {}).get("f1", 0.0)
        s_f1 = stripped.per_tier.get(tier, {}).get("f1", 0.0)
        lines.append(
            f"| `{tier}` | {_fmt_pct(f_f1)} | {_fmt_pct(s_f1)} | "
            f"{(f_f1 - s_f1) * 100:+.1f} |"
        )
    return "\n".join(lines)


def _render_lift_table(lifts: list[ABLiftResult]) -> str:
    lines = [
        "### A/B lift (FULL − STRIPPED)",
        "",
        "| Metric | FULL | STRIPPED | Lift | Interpretation |",
        "|---|---|---|---|---|",
    ]
    for lift in lifts:
        is_pct = lift.metric not in ("avg_fp_on_no_conflict", "count_mae")
        if is_pct:
            full_s = _fmt_pct(lift.full_score)
            strip_s = _fmt_pct(lift.stripped_score)
            lift_s = f"{lift.lift * 100:+.1f}pp"
        else:
            full_s = _fmt_num(lift.full_score)
            strip_s = _fmt_num(lift.stripped_score)
            lift_s = f"{lift.lift:+.3f}"
        lines.append(
            f"| `{lift.metric}` | {full_s} | {strip_s} | {lift_s} | "
            f"`{lift.interpretation}` |"
        )
    return "\n".join(lines)


def _render_per_scenario_detail(
    scenarios: list[Scenario],
    results: list[ScenarioResult],
) -> str:
    by_id = {s.id: s for s in scenarios}
    grouped: dict[tuple[str, str], list[ScenarioResult]] = {}
    for r in results:
        grouped.setdefault((r.scenario_id, r.branch), []).append(r)

    lines = [
        "### Per-scenario detail",
        "",
        "| Scenario | Tier | Branch | Reps | Predicted | Expected | Errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for (sid, branch), rs in sorted(grouped.items()):
        scenario = by_id.get(sid)
        tier = scenario.tier if scenario else "?"
        expected = scenario.expected_total_conflicts if scenario else "?"
        if isinstance(expected, ConflictCountRange):
            expected_s = f"[{expected.min}-{expected.max}]"
        else:
            expected_s = str(expected)
        pred_counts = [str(r.predicted_total) if r.predicted_total is not None else "?" for r in rs]
        n_errors = sum(1 for r in rs if r.error)
        lines.append(
            f"| `{sid}` | {tier} | `{branch}` | {len(rs)} | "
            f"{','.join(pred_counts)} | {expected_s} | {n_errors} |"
        )
    return "\n".join(lines)


def _render_methodology_footer() -> str:
    return (
        "### Methodology disclosure\n\n"
        "- **PDF parsing is mocked.** Both branches receive pre-extracted "
        "clause arrays; this eval tests reasoning, not PyMuPDF robustness. "
        "Documented in `eval/RUBRIC.md` §5 and `eval/runners.py`.\n"
        "- **Prompts mirrored, not imported.** `eval/prompts.py` keeps a "
        "copy of `backend/config.py`'s SYSTEM_PROMPT; a drift-detection "
        "test (`tests/test_runners.py::test_tools_for_eval_mirrors_backend`) "
        "compares them.\n"
        "- **Scorers are deterministic.** No LLM-as-judge. Matching is "
        "canonical-topic + section-overlap (lenient substring either way). "
        "See `eval/scorers.py`.\n"
        "- **Per-tier macro-average.** Overall scores weight each tier "
        "equally, preventing the larger `clear_conflict` tier from dominating.\n"
        "- **is_optional gold conflicts.** Missed optional golds do NOT count "
        "as false negatives (RUBRIC §1 Rule 4 ambiguity carve-out)."
    )


def render_report(
    branch_metrics: list[BranchMetrics],
    lifts: list[ABLiftResult],
    totals_text: str,
    scenario_results: list[ScenarioResult],
    scenarios: Optional[list[Scenario]] = None,
) -> str:
    """Markdown report from aggregated metrics + raw results."""
    full = next((m for m in branch_metrics if m.branch == "full"), None)
    stripped = next((m for m in branch_metrics if m.branch == "stripped"), None)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"# ClauseGuard Eval Report — {timestamp}",
        "",
        "## Headline",
        "",
        _headline(lifts),
        "",
        "## Branch metrics",
        "",
    ]
    if full is not None:
        parts.append(_render_branch_table(full))
    if stripped is not None:
        parts.append(_render_branch_table(stripped))

    if full is not None and stripped is not None:
        parts.append("")
        parts.append(_render_per_tier_breakdown(full, stripped))
        parts.append("")
        parts.append(_render_lift_table(lifts))

    if scenarios:
        parts.append("")
        parts.append(_render_per_scenario_detail(scenarios, scenario_results))

    parts.append("")
    parts.append("## Cost & latency")
    parts.append("")
    parts.append(totals_text)
    parts.append("")
    parts.append(_render_methodology_footer())
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# save_run
# ---------------------------------------------------------------------------


def _serialize_result(r: ScenarioResult) -> dict:
    return r.model_dump(mode="json")


def _serialize_traces(traces: list[CallTrace]) -> list[dict]:
    return [asdict(t) for t in traces]


def save_run(
    report_md: str,
    snapshot: dict,
    reports_dir: Path,
) -> tuple[Path, Path]:
    """Write the markdown report + latest_run.json snapshot."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = reports_dir / f"run_{timestamp}.md"
    json_path = reports_dir / "latest_run.json"
    md_path.write_text(report_md, encoding="utf-8")
    json_path.write_text(
        json.dumps(snapshot, indent=2, default=str),
        encoding="utf-8",
    )
    return md_path, json_path


# ---------------------------------------------------------------------------
# Top-level dispatch (called by CLI)
# ---------------------------------------------------------------------------


def run_and_save(
    scenario_ids: list[str],
    branches: list[str],
    n_reps: int,
    scenarios_dir: Path,
    reports_dir: Path,
    model: str = "claude-sonnet-4-6",
) -> tuple[Path, Path, str]:
    """End-to-end: run eval, score, render, save. Returns (md_path, json_path, report_text)."""
    traces: list[CallTrace] = []
    results = run_eval(
        scenario_ids=scenario_ids,
        branches=branches,
        n_reps=n_reps,
        scenarios_dir=scenarios_dir,
        model=model,
        on_trace=traces.append,
    )
    # Load only the scenarios we ran (and that exist).
    scenarios = [
        load_scenario(scenarios_dir / f"{sid}.json")
        for sid in scenario_ids
        if (scenarios_dir / f"{sid}.json").exists()
    ]
    if not scenarios:
        # Fallback: enumerate everything in the directory (no targeted ids).
        scenarios = list_scenarios(scenarios_dir)

    full_results = [r for r in results if r.branch == "full"]
    stripped_results = [r for r in results if r.branch == "stripped"]
    branch_metrics: list[BranchMetrics] = []
    lifts: list[ABLiftResult] = []
    if full_results:
        branch_metrics.append(
            aggregate_branch_metrics(scenarios, full_results, "full", n_reps)
        )
    if stripped_results:
        branch_metrics.append(
            aggregate_branch_metrics(scenarios, stripped_results, "stripped", n_reps)
        )
    if len(branch_metrics) == 2:
        lifts = compute_ab_lift(branch_metrics[0], branch_metrics[1])

    totals_text = format_totals(aggregate_traces(traces))
    report_md = render_report(
        branch_metrics=branch_metrics,
        lifts=lifts,
        totals_text=totals_text,
        scenario_results=results,
        scenarios=scenarios,
    )
    snapshot = {
        "scenario_ids": scenario_ids,
        "branches": branches,
        "n_reps": n_reps,
        "model": model,
        "results": [_serialize_result(r) for r in results],
        "traces": _serialize_traces(traces),
        "branch_metrics": [m.model_dump(mode="json") for m in branch_metrics],
        "lifts": [lift.model_dump(mode="json") for lift in lifts],
    }
    md_path, json_path = save_run(report_md, snapshot, reports_dir)
    return md_path, json_path, report_md
