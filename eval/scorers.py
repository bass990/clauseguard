"""Deterministic scorers for ClauseGuard eval results. Day-7 implementation.

Five scoring families (per scope spec §5):
  1. score_conflict_detection — precision/recall/F1 via topic+section match
  2. score_risk_tier — strict + lenient accuracy on matched conflicts
  3. score_favor — strict + lenient accuracy on matched conflicts
  4. score_false_positives_no_conflict — FP count on clear_no_conflict tier
  5. score_total_count — MAE on conflict-count calibration

Then aggregate_branch_metrics() folds per-scenario scores into a BranchMetrics
and compute_ab_lift() produces ABLiftResult per metric family.

Matching is greedy: each predicted conflict matches at most one gold and
each gold matches at most one predicted. Two-criteria match (canonical topic
+ section overlap) keeps the matcher tight.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from eval.rubric_audit import topic_to_canonical
from eval.schemas import (
    ABLiftResult,
    BranchMetrics,
    ConflictCountRange,
    DetectionScore,
    ExpectedConflict,
    PredictedConflict,
    Scenario,
    ScenarioResult,
)


LIFT_THRESHOLD = 0.05  # |lift| <= 0.05 is "equivalent" (per scope spec §5)


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _norm_section(s: Optional[str]) -> str:
    """Normalize a section reference for substring comparison."""
    if not s:
        return ""
    return s.lower().strip()


def _sections_overlap(predicted_sec: str, gold_sec: Optional[str]) -> bool:
    """True if predicted section reference plausibly matches gold reference.

    Lenient: substring match either way. The agent might cite '7.1' when the
    gold is '7.1 Limitation of Liability', or vice versa.
    """
    p, g = _norm_section(predicted_sec), _norm_section(gold_sec)
    if not p or not g:
        return False
    return p in g or g in p


def _predicted_matches_gold(
    predicted: PredictedConflict,
    gold: ExpectedConflict,
) -> bool:
    """Match rule (RUBRIC §3): canonical topics equal AND section overlap.

    Section overlap = predicted.company_section overlaps gold_company_section
    OR predicted.vendor_section overlaps gold_vendor_section. If gold has no
    section references at all, fall back to topic-only matching.
    """
    pred_canonical = topic_to_canonical(predicted.topic)
    gold_canonical = topic_to_canonical(gold.topic)
    if pred_canonical is None or pred_canonical != gold_canonical:
        return False

    # If gold has no section refs, topic match alone suffices.
    if not gold.gold_company_section and not gold.gold_vendor_section:
        return True

    company_overlap = _sections_overlap(
        predicted.company_section, gold.gold_company_section
    )
    vendor_overlap = _sections_overlap(
        predicted.vendor_section, gold.gold_vendor_section
    )
    return company_overlap or vendor_overlap


def _greedy_match(
    predicted_conflicts: list[PredictedConflict],
    gold_conflicts: list[ExpectedConflict],
) -> list[tuple[int, int]]:
    """Greedy 1-to-1 matching between predicted and gold conflicts.

    Returns a list of (predicted_idx, gold_idx) pairs. Each index appears
    at most once. Walks predicted in order; for each, takes the first
    unmatched gold that passes _predicted_matches_gold.
    """
    matched_gold: set[int] = set()
    matches: list[tuple[int, int]] = []
    for p_idx, predicted in enumerate(predicted_conflicts):
        for g_idx, gold in enumerate(gold_conflicts):
            if g_idx in matched_gold:
                continue
            if _predicted_matches_gold(predicted, gold):
                matches.append((p_idx, g_idx))
                matched_gold.add(g_idx)
                break
    return matches


# ---------------------------------------------------------------------------
# Family 1: precision / recall / F1
# ---------------------------------------------------------------------------


def score_conflict_detection(
    scenario: Scenario,
    result: ScenarioResult,
) -> DetectionScore:
    """Precision / recall / F1 on conflict detection.

    is_optional gold conflicts: count toward TP if matched, but do NOT count
    toward FN if missed (the agent is allowed to skip them per RUBRIC §1 Rule 4).
    """
    predicted = result.predicted_conflicts or []
    gold = scenario.expected_conflicts

    matches = _greedy_match(predicted, gold)
    matched_pred = {p for p, _ in matches}
    matched_gold = {g for _, g in matches}

    tp = len(matches)
    fp = len(predicted) - len(matched_pred)
    # Missed-but-required = unmatched gold that is NOT optional.
    fn = sum(
        1
        for g_idx, ec in enumerate(gold)
        if g_idx not in matched_gold and not ec.is_optional
    )

    precision = tp / (tp + fp) if (tp + fp) > 0 else _empty_precision(scenario)
    recall = tp / (tp + fn) if (tp + fn) > 0 else _empty_recall(scenario)
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return DetectionScore(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _empty_precision(scenario: Scenario) -> float:
    """Precision when zero predicted: 1.0 on clear_no_conflict (correctly
    silent), 0.0 elsewhere (the system failed to flag anything).
    """
    return 1.0 if scenario.tier == "clear_no_conflict" else 0.0


def _empty_recall(scenario: Scenario) -> float:
    """Recall when there are no required gold conflicts: 1.0 (nothing to recall).

    This handles clear_no_conflict scenarios (zero gold) and ambiguous
    scenarios where all golds are is_optional.
    """
    return 1.0


# ---------------------------------------------------------------------------
# Family 2: risk-tier accuracy
# ---------------------------------------------------------------------------


def score_risk_tier(
    scenario: Scenario,
    result: ScenarioResult,
) -> tuple[float, float]:
    """Risk-tier accuracy on matched conflicts. Returns (strict, lenient).

    1.0 when there are no matched conflicts (vacuously perfect — nothing to
    grade). The aggregator counts these scenarios separately so they don't
    pull the average toward 1.0 spuriously.
    """
    predicted = result.predicted_conflicts or []
    gold = scenario.expected_conflicts
    matches = _greedy_match(predicted, gold)
    if not matches:
        return 1.0, 1.0

    strict_hits = 0
    lenient_hits = 0
    for p_idx, g_idx in matches:
        ec = gold[g_idx]
        risk = predicted[p_idx].risk
        if risk == ec.canonical_risk:
            strict_hits += 1
        if risk in ec.acceptable_risks:
            lenient_hits += 1

    return strict_hits / len(matches), lenient_hits / len(matches)


# ---------------------------------------------------------------------------
# Family 3: favor accuracy
# ---------------------------------------------------------------------------


def score_favor(
    scenario: Scenario,
    result: ScenarioResult,
) -> tuple[float, float]:
    """Favor accuracy on matched conflicts. Returns (strict, lenient)."""
    predicted = result.predicted_conflicts or []
    gold = scenario.expected_conflicts
    matches = _greedy_match(predicted, gold)
    if not matches:
        return 1.0, 1.0

    strict_hits = 0
    lenient_hits = 0
    for p_idx, g_idx in matches:
        ec = gold[g_idx]
        favor = predicted[p_idx].favor
        if favor == ec.canonical_favor:
            strict_hits += 1
        if favor in ec.acceptable_favors:
            lenient_hits += 1

    return strict_hits / len(matches), lenient_hits / len(matches)


# ---------------------------------------------------------------------------
# Family 4: false-positive count
# ---------------------------------------------------------------------------


def score_false_positives_no_conflict(
    scenario: Scenario,
    result: ScenarioResult,
) -> int:
    """Count of predicted conflicts not matched to any gold conflict.

    For clear_no_conflict tier: this equals total predicted (gold is empty).
    For other tiers: count of unmatched predicted (extra flags beyond gold).
    """
    predicted = result.predicted_conflicts or []
    gold = scenario.expected_conflicts
    matches = _greedy_match(predicted, gold)
    matched_pred = {p for p, _ in matches}
    return len(predicted) - len(matched_pred)


# ---------------------------------------------------------------------------
# Family 5: total-count calibration
# ---------------------------------------------------------------------------


def score_total_count(
    scenario: Scenario,
    result: ScenarioResult,
) -> float:
    """Absolute deviation of predicted total from expected.

    For ConflictCountRange: 0 if predicted in [min, max], else distance to
    nearer boundary.
    For int: |predicted - expected|.
    """
    pred_total = result.predicted_total
    if pred_total is None:
        pred_total = len(result.predicted_conflicts or [])

    expected = scenario.expected_total_conflicts
    if isinstance(expected, ConflictCountRange):
        if expected.min <= pred_total <= expected.max:
            return 0.0
        if pred_total < expected.min:
            return float(expected.min - pred_total)
        return float(pred_total - expected.max)
    return float(abs(pred_total - expected))


# ---------------------------------------------------------------------------
# Per-rep aggregation: average a scenario's reps into one score
# ---------------------------------------------------------------------------


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _per_scenario_metrics(
    scenario: Scenario,
    rep_results: list[ScenarioResult],
) -> Optional[dict[str, float]]:
    """Average across the successful reps for one scenario.

    Errored reps (API failure, exhausted credits, timeouts) are excluded
    rather than scored as zero: a billing outage is not evidence about the
    architecture. Returns None when every rep errored, so the scenario drops
    out of the aggregate and is listed in the report's completeness section.
    """
    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []
    risk_strict: list[float] = []
    risk_lenient: list[float] = []
    favor_strict: list[float] = []
    favor_lenient: list[float] = []
    fp_counts: list[float] = []
    count_dev: list[float] = []

    for r in rep_results:
        if r.error:
            continue

        det = score_conflict_detection(scenario, r)
        rs, rl = score_risk_tier(scenario, r)
        fs, fl = score_favor(scenario, r)
        fp = score_false_positives_no_conflict(scenario, r)
        ct = score_total_count(scenario, r)

        precisions.append(det.precision)
        recalls.append(det.recall)
        f1s.append(det.f1)
        risk_strict.append(rs)
        risk_lenient.append(rl)
        favor_strict.append(fs)
        favor_lenient.append(fl)
        fp_counts.append(float(fp))
        count_dev.append(ct)

    if not f1s:
        return None
    return {
        "precision": _avg(precisions),
        "recall": _avg(recalls),
        "f1": _avg(f1s),
        "risk_strict": _avg(risk_strict),
        "risk_lenient": _avg(risk_lenient),
        "favor_strict": _avg(favor_strict),
        "favor_lenient": _avg(favor_lenient),
        "fp_count": _avg(fp_counts),
        "count_dev": _avg(count_dev),
    }


# ---------------------------------------------------------------------------
# Branch aggregation
# ---------------------------------------------------------------------------


def _group_by_scenario(
    results: list[ScenarioResult],
) -> dict[str, list[ScenarioResult]]:
    grouped: dict[str, list[ScenarioResult]] = defaultdict(list)
    for r in results:
        grouped[r.scenario_id].append(r)
    return grouped


def aggregate_branch_metrics(
    scenarios: list[Scenario],
    results: list[ScenarioResult],
    branch: str,
    n_reps: int,
) -> BranchMetrics:
    """Roll up per-scenario per-rep results into one BranchMetrics.

    Macro-averages over scenarios within each tier, then over tiers for
    overall scores. This prevents the larger clear_conflict tier from
    dominating the headline metric. clear_no_conflict's FP-rate metric
    is scoped to that tier (other tiers report unmatched-predicted as FP).
    """
    scenario_by_id = {s.id: s for s in scenarios}
    results_by_scenario = _group_by_scenario(results)

    per_tier_scenario_scores: dict[str, list[dict[str, float]]] = defaultdict(list)
    no_conflict_fp_per_scenario: list[float] = []
    n_errored_runs = sum(1 for r in results if r.error)
    dropped: list[str] = []

    for scenario_id, rep_results in results_by_scenario.items():
        scenario = scenario_by_id.get(scenario_id)
        if scenario is None:
            continue
        per_scenario = _per_scenario_metrics(scenario, rep_results)
        if per_scenario is None:
            dropped.append(scenario_id)
            continue
        per_tier_scenario_scores[scenario.tier].append(per_scenario)
        if scenario.tier == "clear_no_conflict":
            no_conflict_fp_per_scenario.append(per_scenario["fp_count"])

    # Per-tier averages.
    per_tier_metrics: dict[str, dict[str, float]] = {}
    for tier, scenario_scores in per_tier_scenario_scores.items():
        per_tier_metrics[tier] = {
            "n_scenarios": float(len(scenario_scores)),
            "precision": _avg([s["precision"] for s in scenario_scores]),
            "recall": _avg([s["recall"] for s in scenario_scores]),
            "f1": _avg([s["f1"] for s in scenario_scores]),
            "risk_strict": _avg([s["risk_strict"] for s in scenario_scores]),
            "risk_lenient": _avg([s["risk_lenient"] for s in scenario_scores]),
            "favor_strict": _avg([s["favor_strict"] for s in scenario_scores]),
            "favor_lenient": _avg([s["favor_lenient"] for s in scenario_scores]),
            "fp_count": _avg([s["fp_count"] for s in scenario_scores]),
            "count_dev": _avg([s["count_dev"] for s in scenario_scores]),
        }

    # Overall = macro-average across tiers (each tier weighted equally).
    tiers = list(per_tier_metrics.keys())

    def _across_tiers(field: str) -> float:
        return _avg([per_tier_metrics[t][field] for t in tiers])

    return BranchMetrics(
        branch=branch,  # type: ignore[arg-type]
        n_scenarios=sum(int(per_tier_metrics[t]["n_scenarios"]) for t in tiers),
        n_reps=n_reps,
        avg_precision=_across_tiers("precision"),
        avg_recall=_across_tiers("recall"),
        avg_f1=_across_tiers("f1"),
        risk_strict_acc=_across_tiers("risk_strict"),
        risk_lenient_acc=_across_tiers("risk_lenient"),
        favor_strict_acc=_across_tiers("favor_strict"),
        favor_lenient_acc=_across_tiers("favor_lenient"),
        avg_fp_on_no_conflict=_avg(no_conflict_fp_per_scenario),
        count_mae=_across_tiers("count_dev"),
        per_tier=per_tier_metrics,
        n_errored_runs=n_errored_runs,
        scenarios_dropped=sorted(dropped),
    )


# ---------------------------------------------------------------------------
# A/B lift
# ---------------------------------------------------------------------------


def _interpret_lift(
    lift: float,
    threshold: float = LIFT_THRESHOLD,
    *,
    lower_is_better: bool = False,
) -> str:
    """Map a lift value to one of {full_wins, stripped_wins, equivalent}.

    For lower-is-better metrics (FP count, count MAE), flip the direction.
    """
    if lower_is_better:
        lift = -lift
    if lift > threshold:
        return "full_wins"
    if lift < -threshold:
        return "stripped_wins"
    return "equivalent"


def compute_ab_lift(
    full: BranchMetrics,
    stripped: BranchMetrics,
) -> list[ABLiftResult]:
    """Per-metric lift of a candidate branch (`full`) over a baseline (`stripped`).

    The parameter names are historical; any two branches can be compared.
    """
    items = [
        ("precision", full.avg_precision, stripped.avg_precision, False),
        ("recall", full.avg_recall, stripped.avg_recall, False),
        ("f1", full.avg_f1, stripped.avg_f1, False),
        ("risk_strict_acc", full.risk_strict_acc, stripped.risk_strict_acc, False),
        ("risk_lenient_acc", full.risk_lenient_acc, stripped.risk_lenient_acc, False),
        ("favor_strict_acc", full.favor_strict_acc, stripped.favor_strict_acc, False),
        ("favor_lenient_acc", full.favor_lenient_acc, stripped.favor_lenient_acc, False),
        ("avg_fp_on_no_conflict", full.avg_fp_on_no_conflict, stripped.avg_fp_on_no_conflict, True),
        ("count_mae", full.count_mae, stripped.count_mae, True),
    ]
    out: list[ABLiftResult] = []
    for name, full_v, stripped_v, lower_better in items:
        lift = full_v - stripped_v
        interp = _interpret_lift(lift, lower_is_better=lower_better)
        out.append(
            ABLiftResult(
                metric=name,
                candidate=full.branch,
                baseline=stripped.branch,
                full_score=full_v,
                stripped_score=stripped_v,
                lift=lift,
                interpretation=interp,  # type: ignore[arg-type]
            )
        )
    return out
