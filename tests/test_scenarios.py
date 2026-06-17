"""Per-scenario validation + rubric self-check tests.

Discovers every JSON file in eval/scenarios/ and parametrizes:
1. Each loads + validates against the Scenario Pydantic schema.
2. Each scenario's id matches its filename stem.
3. Each scenario's gold conflict topics are a subset of the rubric's
   canonical-conflict candidates (the rubric must AGREE that those topics
   are shared between contracts, else gold cannot claim a conflict).
4. Per-tier invariants: clear_conflict has >=1 conflict, clear_no_conflict
   has zero conflicts AND the rubric's extra candidates (if any) are
   acceptable Rule-2 cases (same topic, same substance, different wording).
5. Tier balance: Day 2 ships >=7 clear_conflict + >=6 clear_no_conflict.

Zero LLM calls. CI-safe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from eval.rubric_audit import rubric_canonical_conflicts, topic_to_canonical
from eval.schemas import Scenario


REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "eval" / "scenarios"


def _scenario_paths() -> list[Path]:
    return sorted(SCENARIOS_DIR.glob("*.json"))


def _load_scenario(path: Path) -> Scenario:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(**data)


def _gold_canonical_topic(topic_str: str) -> Optional[str]:
    """Map a gold-conflict topic string to its canonical bucket via synonyms."""
    return topic_to_canonical(topic_str)


# ---------------------------------------------------------------------------
# Per-scenario parametrized tests
# ---------------------------------------------------------------------------


SCENARIO_PATHS = _scenario_paths()
SCENARIO_IDS = [p.stem for p in SCENARIO_PATHS]


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=SCENARIO_IDS)
def test_scenario_validates_against_schema(scenario_path: Path):
    """Every scenario JSON must validate against the Scenario Pydantic model."""
    _load_scenario(scenario_path)


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=SCENARIO_IDS)
def test_scenario_id_matches_filename(scenario_path: Path):
    """scenario.id must equal the filename stem (enforces consistent IDs)."""
    scenario = _load_scenario(scenario_path)
    assert scenario.id == scenario_path.stem, (
        f"Scenario id '{scenario.id}' does not match filename "
        f"'{scenario_path.stem}'. Rename one to match."
    )


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=SCENARIO_IDS)
def test_scenario_gold_topics_are_rubric_candidates(scenario_path: Path):
    """Every gold conflict's canonical topic must be a rubric-audit candidate.

    If the rubric says 'these two contracts do not share topic X', the
    scenario cannot claim 'X is a conflict'. This catches scenarios where
    the author wrote a gold conflict on a topic the clauses don't actually
    cover (a labeling bug that would inflate the agent's recall trivially).
    """
    scenario = _load_scenario(scenario_path)
    candidates = rubric_canonical_conflicts(
        scenario.company_clauses, scenario.vendor_clauses
    )
    candidate_topics = {c.canonical_topic for c in candidates}

    for ec in scenario.expected_conflicts:
        canonical = _gold_canonical_topic(ec.topic)
        assert canonical is not None, (
            f"Scenario '{scenario.id}': gold conflict topic '{ec.topic}' "
            f"does not map to any canonical bucket. Either fix the topic "
            f"string or extend TOPIC_SYNONYMS in rubric_audit.py."
        )
        assert canonical in candidate_topics, (
            f"Scenario '{scenario.id}': gold conflict topic '{ec.topic}' "
            f"(canonical='{canonical}') is not a rubric candidate. The "
            f"clauses on this topic do not appear in both contracts per "
            f"clauses_by_topic. Rubric candidates were: "
            f"{sorted(candidate_topics)}. Either annotate the relevant "
            f"clauses with canonical_topic='{canonical}' or remove the "
            f"gold conflict."
        )


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=SCENARIO_IDS)
def test_scenario_gold_canonical_risk_matches_rubric(scenario_path: Path):
    """Gold canonical_risk should match the rubric's TOPIC_TO_CANONICAL_RISK.

    Enforced for clear_conflict and clear_no_conflict tiers — these are the
    tiers where the rubric's bucket default IS the right answer.

    Skipped for severity_tiering and ambiguous tiers — those tiers EXIST to
    test deviations from rubric defaults (severity_tiering: agent should
    elevate from default when clause severity warrants; ambiguous: defensible
    multiple risk tiers).
    """
    from eval.rubric_audit import canonical_risk_for  # noqa: PLC0415

    scenario = _load_scenario(scenario_path)
    if scenario.tier in ("severity_tiering", "ambiguous", "adversarial"):
        pytest.skip(
            f"Tier '{scenario.tier}' deliberately tests deviations from "
            f"rubric bucket defaults — skipping rubric-default check."
        )

    for ec in scenario.expected_conflicts:
        canonical = _gold_canonical_topic(ec.topic)
        if canonical is None:
            continue
        rubric_risk = canonical_risk_for(canonical)
        assert rubric_risk in ec.acceptable_risks, (
            f"Scenario '{scenario.id}': gold conflict on '{ec.topic}' "
            f"(canonical='{canonical}') has acceptable_risks={ec.acceptable_risks} "
            f"but the rubric assigns canonical risk='{rubric_risk}'. "
            f"Either add '{rubric_risk}' to acceptable_risks or argue in "
            f"rubric_notes why this scenario justifies a deviation."
        )


# ---------------------------------------------------------------------------
# Per-tier invariants
# ---------------------------------------------------------------------------


CLEAR_CONFLICT_PATHS = [p for p in SCENARIO_PATHS if p.stem.startswith("clear_conflict_")]
CLEAR_NO_CONFLICT_PATHS = [p for p in SCENARIO_PATHS if p.stem.startswith("clear_no_conflict_")]
AMBIGUOUS_PATHS = [p for p in SCENARIO_PATHS if p.stem.startswith("ambiguous_")]
SEVERITY_TIERING_PATHS = [p for p in SCENARIO_PATHS if p.stem.startswith("severity_tiering_")]
ADVERSARIAL_PATHS = [p for p in SCENARIO_PATHS if p.stem.startswith("adversarial_")]


@pytest.mark.parametrize(
    "scenario_path",
    CLEAR_CONFLICT_PATHS,
    ids=[p.stem for p in CLEAR_CONFLICT_PATHS] or ["__no_scenarios__"],
)
def test_clear_conflict_tier_has_at_least_one_gold(scenario_path: Path):
    """clear_conflict tier scenarios must have >=1 expected conflict."""
    if not CLEAR_CONFLICT_PATHS:
        pytest.skip("No clear_conflict scenarios yet.")
    scenario = _load_scenario(scenario_path)
    assert len(scenario.expected_conflicts) >= 1, (
        f"clear_conflict scenario '{scenario.id}' has zero gold conflicts. "
        f"Move to clear_no_conflict tier or add a gold conflict."
    )
    total = scenario.expected_total_conflicts
    if isinstance(total, int):
        assert total >= 1, (
            f"clear_conflict '{scenario.id}': expected_total_conflicts={total} "
            f"must be >=1."
        )


@pytest.mark.parametrize(
    "scenario_path",
    CLEAR_NO_CONFLICT_PATHS,
    ids=[p.stem for p in CLEAR_NO_CONFLICT_PATHS] or ["__no_scenarios__"],
)
def test_clear_no_conflict_tier_has_zero_gold(scenario_path: Path):
    """clear_no_conflict tier scenarios must have zero expected conflicts.

    The schema enforces this; this test makes the contract explicit at the
    scenario-discipline layer and surfaces rubric-candidate counts so we can
    eyeball whether the scenario is exercising Rule 2 (same-substance
    different-wording) or Rule 3 (disjoint topics).
    """
    if not CLEAR_NO_CONFLICT_PATHS:
        pytest.skip("No clear_no_conflict scenarios yet.")
    scenario = _load_scenario(scenario_path)
    assert scenario.expected_conflicts == []
    total = scenario.expected_total_conflicts
    if isinstance(total, int):
        assert total == 0
    # Surface for debugging: how many candidates does the rubric flag?
    # Not an assertion — useful in failure messages elsewhere.
    candidates = rubric_canonical_conflicts(
        scenario.company_clauses, scenario.vendor_clauses
    )
    n_cand = len(candidates)
    # If candidates exist, the scenario is exercising Rule 2; rubric_notes
    # should document this. If candidates is empty, the scenario is exercising
    # Rule 3 (disjoint topics) — also fine.
    notes = scenario.rubric_notes.lower()
    if n_cand > 0:
        rule2_signals = any(
            kw in notes
            for kw in ("rule 2", "rule2", "same substance", "same-substance",
                       "identical substance", "stylistic", "different wording")
        )
        assert rule2_signals, (
            f"clear_no_conflict '{scenario.id}' has {n_cand} rubric "
            f"candidate(s) but rubric_notes does not mention Rule 2 / "
            f"same-substance / stylistic. Document why these candidates "
            f"do not become conflicts."
        )


# ---------------------------------------------------------------------------
# Day 2 balance check
# ---------------------------------------------------------------------------


def test_day_2_scenario_balance():
    """Day 2 ships >=7 clear_conflict + >=6 clear_no_conflict scenarios."""
    assert len(CLEAR_CONFLICT_PATHS) >= 7, (
        f"Day 2 requires >=7 clear_conflict scenarios; "
        f"found {len(CLEAR_CONFLICT_PATHS)}."
    )
    assert len(CLEAR_NO_CONFLICT_PATHS) >= 6, (
        f"Day 2 requires >=6 clear_no_conflict scenarios; "
        f"found {len(CLEAR_NO_CONFLICT_PATHS)}."
    )


def test_day_2_total_scenarios():
    """At least 13 scenarios committed (7+6 Day-2 minimum)."""
    assert len(SCENARIO_PATHS) >= 13, (
        f"Day 2 minimum is 13 scenarios; found {len(SCENARIO_PATHS)}."
    )


# ---------------------------------------------------------------------------
# Day 3 — ambiguous tier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario_path",
    AMBIGUOUS_PATHS,
    ids=[p.stem for p in AMBIGUOUS_PATHS] or ["__no_scenarios__"],
)
def test_ambiguous_tier_uses_count_range_or_optional(scenario_path: Path):
    """Ambiguous tier scenarios should use either ConflictCountRange OR
    is_optional flags on their conflicts (or both). The whole point of the
    tier is that the agent's flag-or-not choice is defensible.
    """
    if not AMBIGUOUS_PATHS:
        pytest.skip("No ambiguous scenarios yet.")
    scenario = _load_scenario(scenario_path)
    from eval.schemas import ConflictCountRange  # noqa: PLC0415

    has_range = isinstance(scenario.expected_total_conflicts, ConflictCountRange)
    has_optional = any(ec.is_optional for ec in scenario.expected_conflicts)
    assert has_range or has_optional, (
        f"ambiguous '{scenario.id}' uses a fixed expected_total_conflicts "
        f"AND no expected_conflicts have is_optional=true. The tier requires "
        f"at least one form of ambiguity marker so the scorer doesn't penalize "
        f"the agent for either choice."
    )


def test_day_3_scenario_balance():
    """Day 3 ships >=6 ambiguous scenarios."""
    assert len(AMBIGUOUS_PATHS) >= 6, (
        f"Day 3 requires >=6 ambiguous scenarios; "
        f"found {len(AMBIGUOUS_PATHS)}."
    )


# ---------------------------------------------------------------------------
# Day 4 — severity_tiering tier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario_path",
    SEVERITY_TIERING_PATHS,
    ids=[p.stem for p in SEVERITY_TIERING_PATHS] or ["__no_scenarios__"],
)
def test_severity_tiering_has_at_least_one_gold(scenario_path: Path):
    """severity_tiering tier scenarios must have >=1 expected conflict (the
    conflict EXISTS and is obvious; the test is which tier the agent picks).
    """
    if not SEVERITY_TIERING_PATHS:
        pytest.skip("No severity_tiering scenarios yet.")
    scenario = _load_scenario(scenario_path)
    assert len(scenario.expected_conflicts) >= 1, (
        f"severity_tiering '{scenario.id}' has zero gold conflicts. "
        f"The tier requires a real conflict to test risk-tier assignment."
    )


@pytest.mark.parametrize(
    "scenario_path",
    SEVERITY_TIERING_PATHS,
    ids=[p.stem for p in SEVERITY_TIERING_PATHS] or ["__no_scenarios__"],
)
def test_severity_tiering_acceptable_risks_narrow(scenario_path: Path):
    """severity_tiering scenarios test tier discipline — acceptable_risks
    should be small (<=2 entries) so the scoring actually penalizes drift.
    """
    if not SEVERITY_TIERING_PATHS:
        pytest.skip("No severity_tiering scenarios yet.")
    scenario = _load_scenario(scenario_path)
    for ec in scenario.expected_conflicts:
        assert len(ec.acceptable_risks) <= 2, (
            f"severity_tiering '{scenario.id}': conflict on '{ec.topic}' has "
            f"acceptable_risks={ec.acceptable_risks} (size {len(ec.acceptable_risks)}). "
            f"The tier's purpose is to score tier accuracy — a 3+ tier set "
            f"defeats that. Tighten to <=2 entries or move to ambiguous tier."
        )


def test_day_4_scenario_balance():
    """Day 4 ships >=5 severity_tiering scenarios."""
    assert len(SEVERITY_TIERING_PATHS) >= 5, (
        f"Day 4 requires >=5 severity_tiering scenarios; "
        f"found {len(SEVERITY_TIERING_PATHS)}."
    )


# ---------------------------------------------------------------------------
# Day 5 — adversarial tier + tier completeness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario_path",
    ADVERSARIAL_PATHS,
    ids=[p.stem for p in ADVERSARIAL_PATHS] or ["__no_scenarios__"],
)
def test_adversarial_tier_validates(scenario_path: Path):
    """Adversarial scenarios still must validate against schema and rubric.

    The adversarial tier tests robustness; nothing about being adversarial
    excuses it from being a valid scenario.
    """
    if not ADVERSARIAL_PATHS:
        pytest.skip("No adversarial scenarios yet.")
    _load_scenario(scenario_path)


def test_day_5_scenario_balance():
    """Day 5 ships >=6 adversarial scenarios."""
    assert len(ADVERSARIAL_PATHS) >= 6, (
        f"Day 5 requires >=6 adversarial scenarios; "
        f"found {len(ADVERSARIAL_PATHS)}."
    )


def test_all_five_tiers_represented():
    """Tier completeness check — every scope-spec tier has at least one
    scenario. Prevents accidental shipping with an empty tier.
    """
    assert len(CLEAR_CONFLICT_PATHS) >= 1
    assert len(CLEAR_NO_CONFLICT_PATHS) >= 1
    assert len(AMBIGUOUS_PATHS) >= 1
    assert len(SEVERITY_TIERING_PATHS) >= 1
    assert len(ADVERSARIAL_PATHS) >= 1


def test_total_scenarios_meets_scope_spec():
    """Scope spec calls for 30 scenarios across 5 tiers."""
    assert len(SCENARIO_PATHS) >= 30, (
        f"Scope spec calls for >=30 scenarios across 5 tiers; "
        f"found {len(SCENARIO_PATHS)}. "
        f"Counts by tier: clear_conflict={len(CLEAR_CONFLICT_PATHS)}, "
        f"clear_no_conflict={len(CLEAR_NO_CONFLICT_PATHS)}, "
        f"ambiguous={len(AMBIGUOUS_PATHS)}, "
        f"severity_tiering={len(SEVERITY_TIERING_PATHS)}, "
        f"adversarial={len(ADVERSARIAL_PATHS)}."
    )
