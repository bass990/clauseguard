"""Pydantic models for the ClauseGuard eval harness.

These types are the contract between scenarios, the runners, and the scorers.
A scenario JSON file must validate against `Scenario`. The runner output
populates `ScenarioResult`. The scorers consume `ScenarioResult` and emit
`BranchMetrics` / `ABLiftResult`.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Risk tiers, mirrored from clauseguard/config.py RISK_LEVELS.
Risk = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

# Favor field per the production system prompt.
Favor = Literal["Company", "Vendor"]

# Tier names — must match scenario file directory conventions.
Tier = Literal[
    "clear_conflict",
    "clear_no_conflict",
    "ambiguous",
    "severity_tiering",
    "adversarial",
]


class Clause(BaseModel):
    """A single contract clause as the agent sees it.

    Mirrors the dict shape returned by tools.extract_clauses() in the
    production system. Scenarios pre-supply these; the eval mocks
    extract_clauses() to return scenario.company_clauses / vendor_clauses
    rather than parsing a real PDF.
    """

    section: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1, max_length=5000)
    party: Literal["company", "vendor"]

    # Optional rubric annotation — the scenario author can tag a clause with
    # its canonical topic to make rubric_audit's job deterministic. If absent,
    # rubric_audit uses substring matching against TOPIC_SYNONYMS.
    canonical_topic: Optional[str] = None


class ExpectedConflict(BaseModel):
    """One gold conflict in a scenario.

    The agent's predicted conflicts are matched against these; see
    scorers.score_conflict_detection() for the matching logic.
    """

    topic: str = Field(..., min_length=1, max_length=200)
    acceptable_topics: list[str] = Field(default_factory=list)
    canonical_risk: Risk
    acceptable_risks: list[Risk] = Field(default_factory=list)
    canonical_favor: Favor
    acceptable_favors: list[Favor] = Field(default_factory=list)
    gold_company_section: Optional[str] = None
    gold_vendor_section: Optional[str] = None
    notes: str = Field(default="", max_length=2000)

    # Rule 4 ambiguity carve-out — see RUBRIC.md §1. If True, the conflict
    # is OPTIONAL: the agent may flag it without penalty, and the agent may
    # also not flag it without penalty. Used in ambiguous tier scenarios.
    is_optional: bool = False

    @model_validator(mode="after")
    def populate_acceptable_sets(self) -> "ExpectedConflict":
        """Default acceptable_* sets to singletons when not specified."""
        if not self.acceptable_topics:
            self.acceptable_topics = [self.topic]
        if not self.acceptable_risks:
            self.acceptable_risks = [self.canonical_risk]
        if not self.acceptable_favors:
            self.acceptable_favors = [self.canonical_favor]
        return self


class ConflictCountRange(BaseModel):
    """Total-conflict-count tolerance for ambiguous-tier scenarios."""

    min: int = Field(..., ge=0)
    max: int = Field(..., ge=0)

    @model_validator(mode="after")
    def check_order(self) -> "ConflictCountRange":
        if self.max < self.min:
            raise ValueError(f"max ({self.max}) must be >= min ({self.min})")
        return self


class Scenario(BaseModel):
    """One gold scenario fixture in eval/scenarios/."""

    id: str = Field(..., pattern=r"^[a-z_]+_\d{3}$")
    tier: Tier
    description: str = Field(..., min_length=10, max_length=500)
    company_clauses: list[Clause] = Field(..., min_length=1)
    vendor_clauses: list[Clause] = Field(..., min_length=1)
    expected_conflicts: list[ExpectedConflict] = Field(default_factory=list)

    # int for exact match (most scenarios) or range for ambiguous tier.
    expected_total_conflicts: int | ConflictCountRange = 0
    rubric_notes: str = Field(default="", max_length=4000)

    @field_validator("expected_total_conflicts")
    @classmethod
    def coerce_total(cls, v):  # noqa: ANN001
        if isinstance(v, dict):
            return ConflictCountRange(**v)
        return v

    @model_validator(mode="after")
    def cross_field_consistency(self) -> "Scenario":
        """Check tier-specific invariants and topic consistency."""
        # clear_no_conflict tier must have zero expected conflicts.
        if self.tier == "clear_no_conflict":
            count = self.expected_total_conflicts
            if isinstance(count, ConflictCountRange):
                if count.max != 0:
                    raise ValueError(
                        f"clear_no_conflict tier '{self.id}' has max>0; "
                        "no-conflict scenarios must have 0 expected conflicts."
                    )
            elif count != 0:
                raise ValueError(
                    f"clear_no_conflict tier '{self.id}' has "
                    f"expected_total_conflicts={count}; must be 0."
                )
            if self.expected_conflicts:
                raise ValueError(
                    f"clear_no_conflict tier '{self.id}' has "
                    f"{len(self.expected_conflicts)} expected_conflicts; must be empty."
                )

        # clear_conflict tier must have >=1 expected conflict.
        if self.tier == "clear_conflict" and not self.expected_conflicts:
            raise ValueError(
                f"clear_conflict tier '{self.id}' has empty expected_conflicts; "
                "must have at least one."
            )

        return self


# ---------------------------------------------------------------------------
# Runtime output types
# ---------------------------------------------------------------------------


class PredictedConflict(BaseModel):
    """A conflict as the agent emits it (10-field schema from system prompt)."""

    id: int
    risk: Risk
    topic: str
    company_section: str
    company_text: str
    vendor_section: str
    vendor_text: str
    conflict_explanation: str
    favor: Favor
    resolution: str


class ScenarioResult(BaseModel):
    """One (scenario, branch, rep) run output."""

    scenario_id: str
    tier: Tier
    branch: Literal["full", "stripped"]
    rep: int

    # Agent output. None if the run errored.
    predicted_conflicts: Optional[list[PredictedConflict]] = None
    predicted_total: Optional[int] = None

    # Bookkeeping.
    error: Optional[str] = None
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Scorer output types
# ---------------------------------------------------------------------------


class ConflictMatch(BaseModel):
    """Result of matching one predicted conflict to a gold conflict (or none)."""

    predicted_idx: Optional[int] = None
    gold_idx: Optional[int] = None
    canonical_topic: Optional[str] = None
    matched: bool = False


class DetectionScore(BaseModel):
    """Precision / recall / F1 on conflict detection for one scenario."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


class BranchMetrics(BaseModel):
    """Aggregated metrics across scenarios for one branch."""

    branch: Literal["full", "stripped"]
    n_scenarios: int
    n_reps: int

    # Overall.
    avg_precision: float
    avg_recall: float
    avg_f1: float

    # Risk-tier accuracy (over matched conflicts).
    risk_strict_acc: float
    risk_lenient_acc: float

    # Favor accuracy (over matched conflicts).
    favor_strict_acc: float
    favor_lenient_acc: float

    # FP rate per scenario on clear_no_conflict tier.
    avg_fp_on_no_conflict: float

    # Total-count calibration.
    count_mae: float

    # Per-tier breakdown — same metrics scoped to each tier.
    per_tier: dict[str, dict[str, float]] = Field(default_factory=dict)


class ABLiftResult(BaseModel):
    """The headline A/B finding for one metric family."""

    metric: str
    full_score: float
    stripped_score: float
    lift: float
    interpretation: Literal[
        "full_wins", "stripped_wins", "equivalent", "investigate"
    ]
