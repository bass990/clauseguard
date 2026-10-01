"""Deterministic scorer tests. Zero LLM calls, CI-safe.

Covers each scoring function across the edge cases that matter:
- Matching: topic-canonical + section-overlap, greedy 1-to-1, fallback when
  gold has no section refs.
- Precision/recall/F1 with TP / FP / FN cases including is_optional handling.
- Risk-tier strict vs lenient.
- Favor strict vs lenient.
- FP count on clear_no_conflict tier.
- Total-count MAE including ConflictCountRange.
- Branch aggregation across tiers (macro average).
- A/B lift interpretation including lower-is-better metrics.
"""

from __future__ import annotations

from typing import Optional

import pytest

from eval.scorers import (
    _greedy_match,
    _interpret_lift,
    _predicted_matches_gold,
    _sections_overlap,
    aggregate_branch_metrics,
    compute_ab_lift,
    score_conflict_detection,
    score_false_positives_no_conflict,
    score_favor,
    score_risk_tier,
    score_total_count,
)
from eval.schemas import (
    ExpectedConflict,
    PredictedConflict,
    Scenario,
    ScenarioResult,
)


def _pc(
    risk: str = "CRITICAL",
    topic: str = "Liability cap",
    company_section: str = "7.1",
    vendor_section: str = "9.2",
    favor: str = "Company",
    id_: int = 1,
) -> PredictedConflict:
    return PredictedConflict(
        id=id_,
        risk=risk,  # type: ignore[arg-type]
        topic=topic,
        company_section=company_section,
        company_text="x",
        vendor_section=vendor_section,
        vendor_text="y",
        conflict_explanation="x conflicts with y",
        favor=favor,  # type: ignore[arg-type]
        resolution="use company language",
    )


def _ec(
    topic: str = "Liability cap",
    canonical_risk: str = "CRITICAL",
    acceptable_risks: Optional[list[str]] = None,
    canonical_favor: str = "Company",
    acceptable_favors: Optional[list[str]] = None,
    gold_company_section: Optional[str] = "7.1",
    gold_vendor_section: Optional[str] = "9.2",
    is_optional: bool = False,
) -> ExpectedConflict:
    return ExpectedConflict(
        topic=topic,
        canonical_risk=canonical_risk,  # type: ignore[arg-type]
        acceptable_risks=acceptable_risks or [],  # type: ignore[arg-type]
        canonical_favor=canonical_favor,  # type: ignore[arg-type]
        acceptable_favors=acceptable_favors or [],  # type: ignore[arg-type]
        gold_company_section=gold_company_section,
        gold_vendor_section=gold_vendor_section,
        is_optional=is_optional,
    )


def _scen(
    tier: str = "clear_conflict",
    expected: Optional[list[ExpectedConflict]] = None,
    total: int = 1,
    company_clauses: Optional[list[dict]] = None,
    vendor_clauses: Optional[list[dict]] = None,
    id_: str = "clear_conflict_001",
) -> Scenario:
    return Scenario(
        id=id_,
        tier=tier,  # type: ignore[arg-type]
        description="Fixture scenario for scorer tests.",
        company_clauses=company_clauses or [
            {"section": "7.1", "text": "x", "party": "company", "canonical_topic": "liability_cap"}
        ],
        vendor_clauses=vendor_clauses or [
            {"section": "9.2", "text": "y", "party": "vendor", "canonical_topic": "liability_cap"}
        ],
        expected_conflicts=expected or ([_ec()] if total > 0 else []),
        expected_total_conflicts=total,
    )


def _result(
    scenario: Scenario,
    predicted: Optional[list[PredictedConflict]] = None,
    branch: str = "full",
    rep: int = 0,
    error: Optional[str] = None,
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario.id,
        tier=scenario.tier,
        branch=branch,  # type: ignore[arg-type]
        rep=rep,
        predicted_conflicts=predicted,
        predicted_total=len(predicted or []),
        error=error,
    )


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def test_sections_overlap_substring_either_way():
    assert _sections_overlap("7.1", "7.1 Limitation of Liability") is True
    assert _sections_overlap("7.1 Limitation of Liability", "7.1") is True
    assert _sections_overlap("Section 7.1", "7.1 Limitation") is False  # neither contains other
    assert _sections_overlap("", "7.1") is False
    assert _sections_overlap("7.1", None) is False


def test_predicted_matches_gold_topic_and_section():
    pred = _pc(topic="Liability cap", company_section="7.1", vendor_section="9.2")
    gold = _ec(
        topic="Limitation of liability",
        gold_company_section="7.1 Limitation of Liability",
        gold_vendor_section="9.2 Liability Cap",
    )
    assert _predicted_matches_gold(pred, gold) is True


def test_predicted_matches_gold_topic_mismatch():
    pred = _pc(topic="Payment terms")
    gold = _ec(topic="Liability cap")
    assert _predicted_matches_gold(pred, gold) is False


def test_predicted_matches_gold_topic_only_when_no_section_refs():
    pred = _pc(topic="Liability cap", company_section="totally_different_section")
    gold = _ec(gold_company_section=None, gold_vendor_section=None)
    # No section refs in gold -> topic match suffices.
    assert _predicted_matches_gold(pred, gold) is True


def test_greedy_match_one_to_one():
    pred = [
        _pc(topic="Liability cap", company_section="7.1", vendor_section="9.2", id_=1),
        _pc(topic="Liability cap", company_section="14.6", vendor_section="9.2", id_=2),
    ]
    gold = [
        _ec(topic="Liability cap", gold_company_section="7.1", gold_vendor_section="9.2"),
        _ec(topic="Liability cap", gold_company_section="14.6", gold_vendor_section="9.2"),
    ]
    matches = _greedy_match(pred, gold)
    # Greedy: each predicted matches at most one gold; each gold used at most once.
    assert len(matches) == 2
    matched_pred = {p for p, _ in matches}
    matched_gold = {g for _, g in matches}
    assert matched_pred == {0, 1}
    assert matched_gold == {0, 1}


# ---------------------------------------------------------------------------
# Family 1: precision / recall / F1
# ---------------------------------------------------------------------------


def test_score_conflict_detection_perfect_match():
    scenario = _scen()
    result = _result(scenario, predicted=[_pc()])
    s = score_conflict_detection(scenario, result)
    assert s.true_positives == 1
    assert s.false_positives == 0
    assert s.false_negatives == 0
    assert s.precision == 1.0
    assert s.recall == 1.0
    assert s.f1 == 1.0


def test_score_conflict_detection_pure_false_positive():
    """One predicted conflict on a clear_no_conflict scenario: 1 FP, P=0, R=1 (nothing to recall)."""
    scenario = _scen(tier="clear_no_conflict", expected=[], total=0)
    result = _result(scenario, predicted=[_pc()])
    s = score_conflict_detection(scenario, result)
    assert s.true_positives == 0
    assert s.false_positives == 1
    assert s.false_negatives == 0
    assert s.precision == 0.0
    assert s.recall == 1.0  # nothing to recall = perfect recall


def test_score_conflict_detection_zero_pred_on_clear_no_conflict():
    """Correctly silent on clear_no_conflict scenario: P=1, R=1, F1=1."""
    scenario = _scen(tier="clear_no_conflict", expected=[], total=0)
    result = _result(scenario, predicted=[])
    s = score_conflict_detection(scenario, result)
    assert s.precision == 1.0
    assert s.recall == 1.0
    assert s.f1 == 1.0


def test_score_conflict_detection_zero_pred_on_clear_conflict_is_failure():
    """Missing the conflict entirely: P=0 (vacuous), R=0, F1=0."""
    scenario = _scen()
    result = _result(scenario, predicted=[])
    s = score_conflict_detection(scenario, result)
    assert s.precision == 0.0
    assert s.recall == 0.0
    assert s.f1 == 0.0


def test_score_conflict_detection_is_optional_does_not_count_against_recall():
    """Missed optional gold conflict should not penalize recall."""
    scenario = _scen(expected=[_ec(is_optional=True)], total=1)
    result = _result(scenario, predicted=[])
    s = score_conflict_detection(scenario, result)
    assert s.false_negatives == 0  # is_optional missing = no penalty
    assert s.recall == 1.0


# ---------------------------------------------------------------------------
# Family 2: risk-tier accuracy
# ---------------------------------------------------------------------------


def test_score_risk_tier_strict_and_lenient():
    scenario = _scen(
        expected=[
            _ec(canonical_risk="CRITICAL", acceptable_risks=["CRITICAL", "HIGH"])
        ]
    )
    # Predicted as HIGH: lenient OK, strict FAIL.
    result = _result(scenario, predicted=[_pc(risk="HIGH")])
    strict, lenient = score_risk_tier(scenario, result)
    assert strict == 0.0
    assert lenient == 1.0


def test_score_risk_tier_no_matches_returns_perfect():
    """Vacuous: nothing to grade."""
    scenario = _scen(tier="clear_no_conflict", expected=[], total=0)
    result = _result(scenario, predicted=[])
    assert score_risk_tier(scenario, result) == (1.0, 1.0)


# ---------------------------------------------------------------------------
# Family 3: favor
# ---------------------------------------------------------------------------


def test_score_favor_strict_and_lenient():
    scenario = _scen(
        expected=[_ec(canonical_favor="Vendor", acceptable_favors=["Vendor", "Company"])]
    )
    result = _result(scenario, predicted=[_pc(favor="Company")])
    strict, lenient = score_favor(scenario, result)
    assert strict == 0.0
    assert lenient == 1.0


# ---------------------------------------------------------------------------
# Family 4: FP count
# ---------------------------------------------------------------------------


def test_score_fp_on_clear_no_conflict_counts_all_predicted():
    scenario = _scen(tier="clear_no_conflict", expected=[], total=0)
    result = _result(
        scenario,
        predicted=[
            _pc(topic="Liability cap", id_=1),
            _pc(topic="Payment terms", company_section="5", vendor_section="8", id_=2),
        ],
    )
    assert score_false_positives_no_conflict(scenario, result) == 2


def test_score_fp_on_clear_conflict_counts_unmatched():
    """One real conflict + one fabricated = 1 unmatched FP."""
    scenario = _scen()
    real = _pc(topic="Liability cap")
    fake = _pc(
        topic="Confidentiality",
        company_section="9.1",
        vendor_section="10.0",
        id_=2,
    )
    result = _result(scenario, predicted=[real, fake])
    assert score_false_positives_no_conflict(scenario, result) == 1


# ---------------------------------------------------------------------------
# Family 5: total-count calibration
# ---------------------------------------------------------------------------


def test_score_total_count_exact_match():
    scenario = _scen(total=1)
    result = _result(scenario, predicted=[_pc()])
    assert score_total_count(scenario, result) == 0.0


def test_score_total_count_over_by_two():
    scenario = _scen(total=1)
    result = _result(
        scenario,
        predicted=[_pc(id_=1), _pc(id_=2), _pc(id_=3)],
    )
    assert score_total_count(scenario, result) == 2.0


def test_score_total_count_in_range_zero():
    """ConflictCountRange: predicted within [min,max] scores 0."""
    scenario = Scenario(
        id="ambiguous_001",
        tier="ambiguous",
        description="Ambiguous scenario with a count range fixture.",
        company_clauses=[
            {"section": "14.1", "text": "30 days", "party": "company", "canonical_topic": "notice_periods"}
        ],
        vendor_clauses=[
            {"section": "16", "text": "35 days", "party": "vendor", "canonical_topic": "notice_periods"}
        ],
        expected_conflicts=[
            _ec(topic="Notice period", canonical_risk="MEDIUM",
                gold_company_section="14.1", gold_vendor_section="16",
                is_optional=True)
        ],
        expected_total_conflicts={"min": 0, "max": 1},
    )
    result_zero = _result(scenario, predicted=[])
    result_one = _result(scenario, predicted=[_pc()])
    result_two = _result(scenario, predicted=[_pc(id_=1), _pc(id_=2)])
    assert score_total_count(scenario, result_zero) == 0.0
    assert score_total_count(scenario, result_one) == 0.0
    assert score_total_count(scenario, result_two) == 1.0  # 1 above max


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_per_scenario_errored_rep_is_excluded_not_zeroed():
    """Errored reps are excluded from the metrics and reported, never scored as 0."""
    scenario = _scen()
    errored = _result(scenario, predicted=None, error="boom")
    metrics = aggregate_branch_metrics(
        scenarios=[scenario],
        results=[errored],
        branch="full",
        n_reps=1,
    )
    assert metrics.n_scenarios == 0
    assert metrics.n_errored_runs == 1
    assert metrics.scenarios_dropped == [scenario.id]
    assert metrics.avg_precision == 0.0  # nothing scored, not a real zero

    # one errored rep next to one good rep: the good rep alone defines the score
    good = _result(scenario, predicted=[], rep=1)
    metrics2 = aggregate_branch_metrics(scenarios=[scenario], results=[errored, good], branch="full", n_reps=2)
    assert metrics2.n_scenarios == 1 and metrics2.n_errored_runs == 1 and metrics2.scenarios_dropped == []


# ---------------------------------------------------------------------------
# Branch aggregation
# ---------------------------------------------------------------------------


def test_aggregate_branch_metrics_macro_average_across_tiers():
    """clear_conflict scenario perfect, clear_no_conflict scenario perfect.
    Each tier weighted equally: overall precision = 1.0, recall = 1.0."""
    s1 = _scen(tier="clear_conflict", id_="clear_conflict_001")
    s2 = _scen(tier="clear_no_conflict", expected=[], total=0, id_="clear_no_conflict_001")
    r1 = _result(s1, predicted=[_pc()])
    r2 = _result(s2, predicted=[])
    metrics = aggregate_branch_metrics(
        scenarios=[s1, s2], results=[r1, r2], branch="full", n_reps=1
    )
    assert metrics.n_scenarios == 2
    assert metrics.avg_precision == 1.0
    assert metrics.avg_recall == 1.0
    assert metrics.avg_f1 == 1.0
    assert metrics.avg_fp_on_no_conflict == 0.0
    assert "clear_conflict" in metrics.per_tier
    assert "clear_no_conflict" in metrics.per_tier


def test_aggregate_branch_metrics_per_tier_breakdown():
    """A failure on one tier shouldn't pollute the other tier's score."""
    s1 = _scen(tier="clear_conflict", id_="clear_conflict_001")
    s2 = _scen(tier="clear_no_conflict", expected=[], total=0, id_="clear_no_conflict_001")
    # clear_conflict perfect; clear_no_conflict has 1 FP.
    r1 = _result(s1, predicted=[_pc()])
    r2 = _result(s2, predicted=[_pc()])
    metrics = aggregate_branch_metrics(
        scenarios=[s1, s2], results=[r1, r2], branch="full", n_reps=1
    )
    assert metrics.per_tier["clear_conflict"]["precision"] == 1.0
    assert metrics.per_tier["clear_no_conflict"]["precision"] == 0.0
    assert metrics.avg_fp_on_no_conflict == 1.0


# ---------------------------------------------------------------------------
# A/B lift interpretation
# ---------------------------------------------------------------------------


def test_interpret_lift_higher_is_better():
    assert _interpret_lift(0.10, lower_is_better=False) == "full_wins"
    assert _interpret_lift(-0.10, lower_is_better=False) == "stripped_wins"
    assert _interpret_lift(0.02, lower_is_better=False) == "equivalent"


def test_interpret_lift_lower_is_better_inverted():
    """For FP-count / count-MAE: lower is better, so positive lift = stripped_wins."""
    assert _interpret_lift(0.10, lower_is_better=True) == "stripped_wins"
    assert _interpret_lift(-0.10, lower_is_better=True) == "full_wins"
    assert _interpret_lift(0.02, lower_is_better=True) == "equivalent"


def test_compute_ab_lift_emits_one_per_metric():
    """compute_ab_lift returns 9 entries — one per metric family."""
    s = _scen(tier="clear_conflict")
    full_metrics = aggregate_branch_metrics(
        scenarios=[s], results=[_result(s, predicted=[_pc()])], branch="full", n_reps=1
    )
    stripped_metrics = aggregate_branch_metrics(
        scenarios=[s], results=[_result(s, predicted=[], branch="stripped")],
        branch="stripped", n_reps=1
    )
    lifts = compute_ab_lift(full_metrics, stripped_metrics)
    assert len(lifts) == 9
    names = {lift.metric for lift in lifts}
    assert "precision" in names
    assert "recall" in names
    assert "f1" in names
    assert "risk_strict_acc" in names
    assert "count_mae" in names


def test_compute_ab_lift_chainpilot_style_finding():
    """If stripped beats full on f1 by more than threshold, interpretation
    should be 'stripped_wins' — mirroring ChainPilot's -13.7pp finding."""
    s_full = _scen(tier="clear_conflict", id_="clear_conflict_001")
    s_strip = _scen(tier="clear_conflict", id_="clear_conflict_001")
    # FULL misses the conflict; STRIPPED catches it.
    full_metrics = aggregate_branch_metrics(
        scenarios=[s_full], results=[_result(s_full, predicted=[])],
        branch="full", n_reps=1
    )
    stripped_metrics = aggregate_branch_metrics(
        scenarios=[s_strip], results=[_result(s_strip, predicted=[_pc()], branch="stripped")],
        branch="stripped", n_reps=1
    )
    lifts = compute_ab_lift(full_metrics, stripped_metrics)
    f1_lift = next(lift for lift in lifts if lift.metric == "f1")
    assert f1_lift.full_score == 0.0
    assert f1_lift.stripped_score == 1.0
    assert f1_lift.interpretation == "stripped_wins"
    assert f1_lift.lift == pytest.approx(-1.0)
