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
import sys
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
    RUNNERS,
    list_scenarios,
    load_scenario,
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
    try:
        return RUNNERS[branch]
    except KeyError:
        raise ValueError(f"Unknown branch: {branch}") from None


FATAL_ERROR_MARKERS = (
    "credit balance",          # billing exhausted: every further call fails identically
    "authentication_error",
    "invalid x-api-key",
    "permission_error",
)


def is_fatal_error(message: Optional[str]) -> bool:
    """True for errors that will repeat on every call (billing, auth).

    Continuing past one of these burns wall-clock producing hundreds of
    identical failures and a report full of holes; the run stops instead
    and can be resumed once the account is fixed.
    """
    m = (message or "").lower()
    return any(marker in m for marker in FATAL_ERROR_MARKERS)


def run_eval(
    scenario_ids: list[str],
    branches: list[str],
    n_reps: int,
    scenarios_dir: Path,
    model: str = "claude-sonnet-5",
    on_trace=None,
    prior_results: Optional[dict[tuple[str, str, int], ScenarioResult]] = None,
    state: Optional[dict] = None,
    on_result=None,
) -> list[ScenarioResult]:
    """Run scenarios × branches × reps. Errors captured per-result.

    `prior_results` (keyed by (scenario_id, branch, rep)) lets a run resume:
    successful prior runs are reused without new model calls. `state`, when
    given, receives `aborted` (the fatal error that stopped the run) and
    `completed` (number of runs executed or reused). `on_result` is called
    after every run so the caller can checkpoint.
    """
    results: list[ScenarioResult] = []
    prior = prior_results or {}
    state = state if state is not None else {}
    state.setdefault("aborted", None)
    state.setdefault("completed", 0)
    state.setdefault("reused", 0)
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
                if state["aborted"]:
                    return results
                reused = prior.get((scenario_id, branch, rep))
                if reused is not None and not reused.error:
                    results.append(reused)
                    state["reused"] += 1
                    state["completed"] += 1
                    continue
                result = runner(
                    scenario=scenario,
                    rep=rep,
                    model=model,
                    on_trace=on_trace,
                )
                results.append(result)
                state["completed"] += 1
                if on_result is not None:
                    on_result(result)
                if is_fatal_error(result.error):
                    state["aborted"] = result.error
                    sys.stderr.write(f"\nABORTING run after {state['completed']} runs — fatal API error: {result.error}\n"
                                     "Fix the account, then re-run with --resume to continue from this point.\n")
    return results


def load_prior_results(snapshot: dict) -> tuple[dict[tuple[str, str, int], ScenarioResult], list[CallTrace]]:
    """Successful results + their traces from a saved latest_run.json."""
    prior: dict[tuple[str, str, int], ScenarioResult] = {}
    for raw in snapshot.get("results", []):
        r = ScenarioResult(**raw)
        if not r.error:
            prior[(r.scenario_id, r.branch, r.rep)] = r
    traces = [
        CallTrace(**t) for t in snapshot.get("traces", [])
        if (t.get("scenario_id"), t.get("branch"), t.get("rep")) in prior
    ]
    return prior, traces


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_num(x: float) -> str:
    return f"{x:.3f}"


def _headline(lifts: list[ABLiftResult], lifts_by_branch: Optional[dict[str, list[ABLiftResult]]] = None) -> str:
    """One-paragraph headline framing the A/B finding (full vs stripped),
    followed by a one-line ranking of every branch when more ran."""
    f1 = next((lift for lift in lifts if lift.metric == "f1"), None)
    if f1 is None:
        return "_(No F1 lift to summarize.)_"
    extra = ""
    if lifts_by_branch and len(lifts_by_branch) > 1:
        ranked = sorted(
            ((b, next(x for x in ls if x.metric == "f1")) for b, ls in lifts_by_branch.items()),
            key=lambda kv: -kv[1].full_score,
        )
        extra = "\n\nAll branches vs `stripped` on F1: " + ", ".join(
            f"`{b}` {_fmt_pct(x.full_score)} ({x.lift * 100:+.1f}pp)" for b, x in ranked
        ) + f"; `stripped` {_fmt_pct(f1.stripped_score)}."
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
    return verdict + extra


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


def _render_per_tier_breakdown(branch_metrics: list[BranchMetrics]) -> str:
    """Per-tier F1 for every branch, with each branch's lift over `stripped`."""
    tiers = sorted({t for m in branch_metrics for t in m.per_tier})
    stripped = next((m for m in branch_metrics if m.branch == "stripped"), None)
    header = "| Tier | " + " | ".join(f"`{m.branch}` F1" for m in branch_metrics)
    if stripped is not None:
        header += " | " + " | ".join(f"`{m.branch}` vs stripped (pp)" for m in branch_metrics if m.branch != "stripped")
    header += " |"
    lines = ["### Per-tier F1 breakdown", "", header, "|" + "---|" * (header.count("|") - 1)]
    for tier in tiers:
        row = f"| `{tier}` | " + " | ".join(_fmt_pct(m.per_tier.get(tier, {}).get("f1", 0.0)) for m in branch_metrics)
        if stripped is not None:
            base = stripped.per_tier.get(tier, {}).get("f1", 0.0)
            row += " | " + " | ".join(
                f"{(m.per_tier.get(tier, {}).get('f1', 0.0) - base) * 100:+.1f}" for m in branch_metrics if m.branch != "stripped"
            )
        lines.append(row + " |")
    return "\n".join(lines)


def _render_variance(scenarios: list[Scenario], results: list[ScenarioResult]) -> str:
    """Run-to-run variance: per-branch mean range of per-scenario F1 across reps."""
    from eval.scorers import score_conflict_detection  # noqa: PLC0415

    by_id = {s.id: s for s in scenarios}
    grouped: dict[tuple[str, str], list[float]] = {}
    for r in results:
        sc = by_id.get(r.scenario_id)
        if sc is None or r.error:
            continue
        grouped.setdefault((r.branch, r.scenario_id), []).append(score_conflict_detection(sc, r).f1)
    per_branch: dict[str, list[float]] = {}
    unstable: dict[str, int] = {}
    for (branch, _sid), f1s in grouped.items():
        if len(f1s) < 2:
            continue
        rng = max(f1s) - min(f1s)
        per_branch.setdefault(branch, []).append(rng)
        if rng >= 0.5:
            unstable[branch] = unstable.get(branch, 0) + 1
    if not per_branch:
        return "### Run-to-run variance\n\n_(single rep: no variance estimate)_"
    lines = ["### Run-to-run variance", "",
             "Mean per-scenario F1 range across reps (0 = identical every rep). Scenarios whose F1 swung by 0.5 or more "
             "are listed as unstable: any lift smaller than this band is noise.", "",
             "| Branch | Mean F1 range | Unstable scenarios |", "|---|---|---|"]
    for branch, ranges in sorted(per_branch.items()):
        lines.append(f"| `{branch}` | {sum(ranges) / len(ranges):.3f} | {unstable.get(branch, 0)} / {len(ranges)} |")
    return "\n".join(lines)


def _render_routing(results: list[ScenarioResult]) -> str:
    routed = [r for r in results if r.branch == "routed" and r.route]
    if not routed:
        return ""
    by_tier: dict[str, dict[str, int]] = {}
    sources: dict[str, int] = {}
    for r in routed:
        by_tier.setdefault(r.tier, {"agentic": 0, "single": 0})[r.route] += 1
        sources[r.route_source or "?"] = sources.get(r.route_source or "?", 0) + 1
    lines = ["### Routing decisions (routed branch)", "", "| Tier | agentic | single |", "|---|---|---|"]
    for tier, c in sorted(by_tier.items()):
        lines.append(f"| `{tier}` | {c['agentic']} | {c['single']} |")
    lines.append("")
    lines.append("Decision source: " + ", ".join(f"{k} {v}" for k, v in sorted(sources.items())))
    return "\n".join(lines)


def _render_playbook_usage(results: list[ScenarioResult]) -> str:
    rows = []
    for branch in ("full_rag", "stripped_rag", "routed"):
        rs = [r for r in results if r.branch == branch and not r.error]
        if rs:
            rows.append(f"| `{branch}` | {sum(r.playbook_calls for r in rs) / len(rs):.1f} | "
                        f"{sum(r.schema_retries for r in rs)} |")
    if not rows:
        return ""
    return "\n".join(["### Playbook and schema", "", "| Branch | Playbook lookups per run | Schema-repair rounds (total) |",
                       "|---|---|---|"] + rows)


def _render_lift_table(lifts: list[ABLiftResult]) -> str:
    cand = lifts[0].candidate if lifts else "full"
    base = lifts[0].baseline if lifts else "stripped"
    lines = [
        f"### A/B lift (`{cand}` − `{base}`)",
        "",
        f"| Metric | `{cand}` | `{base}` | Lift | Interpretation |",
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
        "- **Production prompt and tool schemas imported, not mirrored.** "
        "`eval/prompts.py` imports `config.SYSTEM_PROMPT`; `eval/runners.py` "
        "uses `backend.tools.TOOLS`; `lookup_playbook` and the schema "
        "validator are the production functions.\n"
        "- **Scorers are deterministic.** No LLM-as-judge. Matching is "
        "canonical-topic + section-overlap (lenient substring either way). "
        "See `eval/scorers.py`.\n"
        "- **Per-tier macro-average.** Overall scores weight each tier "
        "equally, preventing the larger `clear_conflict` tier from dominating.\n"
        "- **is_optional gold conflicts.** Missed optional golds do NOT count "
        "as false negatives (RUBRIC §1 Rule 4 ambiguity carve-out)."
    )


def _render_completeness(
    scenario_results: list[ScenarioResult],
    branch_metrics: list[BranchMetrics],
    planned_runs: Optional[int],
    aborted: Optional[str],
) -> str:
    """How much of the planned run actually produced scorable output."""
    n_ok = sum(1 for r in scenario_results if not r.error)
    n_err = sum(1 for r in scenario_results if r.error)
    n_missing = max(0, (planned_runs or 0) - len(scenario_results)) if planned_runs else 0
    lines = ["## Completeness", ""]
    if n_err == 0 and n_missing == 0 and not aborted:
        lines.append(f"All {n_ok} planned runs completed. Every metric below uses every run.")
        return "\n".join(lines)
    lines.append("**⚠ PARTIAL RUN — treat every number below as provisional.**")
    lines.append("")
    lines.append(f"- runs scored: {n_ok}")
    lines.append(f"- runs errored (excluded from all metrics): {n_err}")
    if n_missing:
        lines.append(f"- runs never executed (aborted early): {n_missing}")
    if aborted:
        lines.append(f"- aborted on fatal API error: `{aborted[:160]}`")
        lines.append("- resume with `python -m eval.runners --mode full --resume --yes` once the account is fixed")
    lines.append("")
    lines.append("| Branch | scored | errored | scenarios dropped (all reps errored) |")
    lines.append("|---|---|---|---|")
    for m in branch_metrics:
        rs = [r for r in scenario_results if r.branch == m.branch]
        ok = sum(1 for r in rs if not r.error)
        dropped = ", ".join(f"`{s}`" for s in m.scenarios_dropped) or "—"
        lines.append(f"| `{m.branch}` | {ok} | {m.n_errored_runs} | {dropped} |")
    return "\n".join(lines)


def render_report(
    branch_metrics: list[BranchMetrics],
    lifts: list[ABLiftResult],
    totals_text: str,
    scenario_results: list[ScenarioResult],
    scenarios: Optional[list[Scenario]] = None,
    lifts_by_branch: Optional[dict[str, list[ABLiftResult]]] = None,
    model: Optional[str] = None,
    planned_runs: Optional[int] = None,
    aborted: Optional[str] = None,
) -> str:
    """Markdown report from aggregated metrics + raw results."""
    stripped = next((m for m in branch_metrics if m.branch == "stripped"), None)
    partial = aborted or any(r.error for r in scenario_results)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"# ClauseGuard Eval Report — {timestamp}",
        "",
        f"_model: `{model}`_" if model else "",
        "",
        "## Headline",
        "",
        ("**⚠ PARTIAL RUN** (see Completeness). " if partial else "") + _headline(lifts, lifts_by_branch),
        "",
        _render_completeness(scenario_results, branch_metrics, planned_runs, aborted),
        "",
        "## Branch metrics",
        "",
    ]
    for m in branch_metrics:
        parts.append(_render_branch_table(m))

    if len(branch_metrics) >= 2:
        parts.append("")
        parts.append(_render_per_tier_breakdown(branch_metrics))
    for _cand, ls in (lifts_by_branch or ({"full": lifts} if lifts else {})).items():
        if stripped is not None and ls:
            parts.append("")
            parts.append(_render_lift_table(ls))
    if scenarios:
        parts.append("")
        parts.append(_render_variance(scenarios, scenario_results))
    routing = _render_routing(scenario_results)
    if routing:
        parts.append("")
        parts.append(routing)
    playbook = _render_playbook_usage(scenario_results)
    if playbook:
        parts.append("")
        parts.append(playbook)

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
    model: str = "claude-sonnet-5",
    resume_snapshot: Optional[dict] = None,
) -> tuple[Path, Path, str]:
    """End-to-end: run eval, score, render, save. Returns (md_path, json_path, report_text).

    With `resume_snapshot` (a previous latest_run.json), successful runs are
    reused and only missing or errored (scenario, branch, rep) cells run.
    A checkpoint of raw results is written after every run so an interrupted
    run loses at most one call.
    """
    traces: list[CallTrace] = []
    prior: dict = {}
    if resume_snapshot:
        prior, prior_traces = load_prior_results(resume_snapshot)
        traces.extend(prior_traces)
        sys.stderr.write(f"Resuming: {len(prior)} successful runs reused from the previous snapshot.\n")
    state: dict = {}
    reports_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = reports_dir / "checkpoint.jsonl"
    checkpoint.write_text("", encoding="utf-8")

    def _checkpoint(r: ScenarioResult) -> None:
        with checkpoint.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_serialize_result(r), default=str) + "\n")

    results = run_eval(
        scenario_ids=scenario_ids,
        branches=branches,
        n_reps=n_reps,
        scenarios_dir=scenarios_dir,
        model=model,
        on_trace=traces.append,
        prior_results=prior,
        state=state,
        on_result=_checkpoint,
    )
    planned_runs = len(scenario_ids) * len(branches) * n_reps
    # Load only the scenarios we ran (and that exist).
    scenarios = [
        load_scenario(scenarios_dir / f"{sid}.json")
        for sid in scenario_ids
        if (scenarios_dir / f"{sid}.json").exists()
    ]
    if not scenarios:
        # Fallback: enumerate everything in the directory (no targeted ids).
        scenarios = list_scenarios(scenarios_dir)

    branch_metrics: list[BranchMetrics] = []
    for branch in branches:
        br = [r for r in results if r.branch == branch]
        if br:
            branch_metrics.append(aggregate_branch_metrics(scenarios, br, branch, n_reps))
    stripped_m = next((m for m in branch_metrics if m.branch == "stripped"), None)
    lifts_by_branch: dict[str, list[ABLiftResult]] = {}
    if stripped_m is not None:
        for m in branch_metrics:
            if m.branch != "stripped":
                lifts_by_branch[m.branch] = compute_ab_lift(m, stripped_m)
    lifts: list[ABLiftResult] = lifts_by_branch.get("full", [])
    if not lifts and lifts_by_branch:
        lifts = next(iter(lifts_by_branch.values()))

    totals_text = format_totals(aggregate_traces(traces))
    report_md = render_report(
        branch_metrics=branch_metrics,
        lifts=lifts,
        totals_text=totals_text,
        scenario_results=results,
        scenarios=scenarios,
        lifts_by_branch=lifts_by_branch,
        model=model,
        planned_runs=planned_runs,
        aborted=state.get("aborted"),
    )
    snapshot = {
        "scenario_ids": scenario_ids,
        "branches": branches,
        "n_reps": n_reps,
        "model": model,
        "planned_runs": planned_runs,
        "completed_runs": len(results),
        "errored_runs": sum(1 for r in results if r.error),
        "reused_runs": state.get("reused", 0),
        "aborted": state.get("aborted"),
        "results": [_serialize_result(r) for r in results],
        "traces": _serialize_traces(traces),
        "branch_metrics": [m.model_dump(mode="json") for m in branch_metrics],
        "lifts": [lift.model_dump(mode="json") for lift in lifts],
        "lifts_by_branch": {b: [x.model_dump(mode="json") for x in ls] for b, ls in lifts_by_branch.items()},
    }
    md_path, json_path = save_run(report_md, snapshot, reports_dir)
    return md_path, json_path, report_md


def rerender_snapshot(reports_dir: Path, scenarios_dir: Path) -> Path:
    """Re-score and re-render reports/latest_run.json without model calls.

    Used after a scorer or report change so the committed numbers reflect the
    current scoring rules on the same raw model outputs.
    """
    snap = json.loads((reports_dir / "latest_run.json").read_text(encoding="utf-8"))
    results = [ScenarioResult(**r) for r in snap["results"]]
    traces = [CallTrace(**t) for t in snap.get("traces", [])]
    scenario_ids = snap["scenario_ids"]
    branches = snap["branches"]
    n_reps = int(snap["n_reps"])
    model = snap.get("model", "?")
    scenarios = [
        load_scenario(scenarios_dir / f"{sid}.json")
        for sid in scenario_ids
        if (scenarios_dir / f"{sid}.json").exists()
    ]
    branch_metrics: list[BranchMetrics] = []
    for branch in branches:
        br = [r for r in results if r.branch == branch]
        if br:
            branch_metrics.append(aggregate_branch_metrics(scenarios, br, branch, n_reps))
    stripped_m = next((m for m in branch_metrics if m.branch == "stripped"), None)
    lifts_by_branch: dict[str, list[ABLiftResult]] = {}
    if stripped_m is not None:
        for m in branch_metrics:
            if m.branch != "stripped":
                lifts_by_branch[m.branch] = compute_ab_lift(m, stripped_m)
    lifts = lifts_by_branch.get("full", []) or (next(iter(lifts_by_branch.values())) if lifts_by_branch else [])
    planned = snap.get("planned_runs") or len(scenario_ids) * len(branches) * n_reps
    report_md = render_report(
        branch_metrics=branch_metrics, lifts=lifts, totals_text=format_totals(aggregate_traces(traces)),
        scenario_results=results, scenarios=scenarios, lifts_by_branch=lifts_by_branch, model=model,
        planned_runs=planned, aborted=snap.get("aborted"),
    )
    snap["branch_metrics"] = [m.model_dump(mode="json") for m in branch_metrics]
    snap["lifts"] = [x.model_dump(mode="json") for x in lifts]
    snap["lifts_by_branch"] = {b: [x.model_dump(mode="json") for x in ls] for b, ls in lifts_by_branch.items()}
    snap["errored_runs"] = sum(1 for r in results if r.error)
    md_path, _ = save_run(report_md, snap, reports_dir)
    return md_path
