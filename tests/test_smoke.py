"""Day-1 smoke tests for the ClauseGuard eval harness.

No LLM calls. No network. CI-safe. Verifies:
- eval package is importable
- RUBRIC.md is committed before scenarios
- instrumentation cost arithmetic is correct against pricing table
- runners CLI exits non-zero with Day-1 status on --mode dry
- rubric_audit topic normalization and synonym lookup work
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = REPO_ROOT / "eval"


# ---------------------------------------------------------------------------
# Package wiring
# ---------------------------------------------------------------------------


def test_eval_package_importable():
    from eval import schemas, instrumentation, rubric_audit, prompts  # noqa: F401, PLC0415


def test_rubric_committed_before_scenarios():
    """RUBRIC.md must exist; scenarios directory may be empty Day 1."""
    rubric = EVAL_DIR / "RUBRIC.md"
    scenarios = EVAL_DIR / "scenarios"
    assert rubric.exists(), "RUBRIC.md must be committed Day 1"
    rubric_text = rubric.read_text(encoding="utf-8")
    assert "Status:" in rubric_text
    assert "What counts as a" in rubric_text
    assert scenarios.exists() and scenarios.is_dir()


def test_readme_documents_branches():
    readme = (EVAL_DIR / "README.md").read_text(encoding="utf-8")
    assert "FULL branch" in readme
    assert "STRIPPED branch" in readme
    assert "A/B" in readme


# ---------------------------------------------------------------------------
# Instrumentation cost arithmetic
# ---------------------------------------------------------------------------


def test_cost_for_call_sonnet_4_6():
    from eval.instrumentation import cost_for_call  # noqa: PLC0415

    # 1M input + 1M output at sonnet 4.6 should be exactly $3 + $15 = $18.
    cost = cost_for_call("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert abs(cost - 18.0) < 1e-9


def test_cost_for_call_haiku_4_5():
    from eval.instrumentation import cost_for_call  # noqa: PLC0415

    # 1M input + 1M output at haiku 4.5 should be $0.25 + $1.25 = $1.50.
    cost = cost_for_call("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert abs(cost - 1.50) < 1e-9


def test_cost_for_call_unknown_model_falls_back():
    from eval.instrumentation import cost_for_call  # noqa: PLC0415

    # Unknown model uses fallback sonnet pricing — should match sonnet.
    sonnet = cost_for_call("claude-sonnet-4-6", 5_000, 1_000)
    unknown = cost_for_call("claude-future-model", 5_000, 1_000)
    assert abs(sonnet - unknown) < 1e-12


def test_cost_for_call_typical_scenario():
    from eval.instrumentation import cost_for_call  # noqa: PLC0415

    # Per scope spec: ≈5K input + ≈3K output per FULL scenario ≈ $0.06.
    cost = cost_for_call("claude-sonnet-4-6", 5_000, 3_000)
    assert 0.05 < cost < 0.07


def test_make_trace_computes_cost():
    from eval.instrumentation import make_trace  # noqa: PLC0415

    trace = make_trace(
        model="claude-sonnet-4-6",
        role="agent",
        input_tokens=5_000,
        output_tokens=3_000,
        duration_seconds=4.2,
        scenario_id="clear_conflict_001",
        branch="full",
        rep=0,
    )
    assert trace.model == "claude-sonnet-4-6"
    assert trace.scenario_id == "clear_conflict_001"
    assert 0.05 < trace.cost_usd < 0.07


def test_aggregate_traces_per_role_rollup():
    from eval.instrumentation import aggregate_traces, make_trace  # noqa: PLC0415

    traces = [
        make_trace("claude-sonnet-4-6", "agent", 5_000, 3_000, 4.0),
        make_trace("claude-sonnet-4-6", "agent", 5_000, 3_000, 4.0),
        make_trace("claude-sonnet-4-6", "stripped", 4_000, 3_000, 3.0),
    ]
    totals = aggregate_traces(traces)
    assert totals.n_calls == 3
    assert totals.total_input_tokens == 14_000
    assert totals.total_output_tokens == 9_000
    assert "agent" in totals.per_role
    assert "stripped" in totals.per_role
    assert totals.per_role["agent"]["n_calls"] == 2
    assert totals.per_role["stripped"]["n_calls"] == 1


def test_format_totals_renders():
    from eval.instrumentation import (  # noqa: PLC0415
        aggregate_traces,
        format_totals,
        make_trace,
    )

    traces = [make_trace("claude-sonnet-4-6", "agent", 5_000, 3_000, 4.0)]
    output = format_totals(aggregate_traces(traces))
    assert "Total calls" in output
    assert "Total cost" in output
    assert "$" in output


# ---------------------------------------------------------------------------
# Rubric audit — synonym lookup
# ---------------------------------------------------------------------------


def test_topic_to_canonical_liability():
    from eval.rubric_audit import topic_to_canonical  # noqa: PLC0415

    assert topic_to_canonical("Liability cap") == "liability_cap"
    assert topic_to_canonical("Limitation of Liability") == "liability_cap"
    assert topic_to_canonical("damages cap") == "liability_cap"


def test_topic_to_canonical_payment_terms_beats_payment():
    from eval.rubric_audit import topic_to_canonical  # noqa: PLC0415

    # Longest-synonym-first ordering prevents "payment" matching before
    # "payment terms" in the lookup.
    assert topic_to_canonical("Payment Terms") == "payment_terms"
    assert topic_to_canonical("payment") == "payment_terms"


def test_topic_to_canonical_unknown_returns_none():
    from eval.rubric_audit import topic_to_canonical  # noqa: PLC0415

    assert topic_to_canonical("blockchain custody") is None
    assert topic_to_canonical("") is None


def test_canonical_risk_lookup_matches_rubric():
    from eval.rubric_audit import canonical_risk_for  # noqa: PLC0415

    # Spot-check each tier per RUBRIC.md §2.
    assert canonical_risk_for("liability_cap") == "CRITICAL"
    assert canonical_risk_for("indemnification") == "CRITICAL"
    assert canonical_risk_for("payment_terms") == "HIGH"
    assert canonical_risk_for("confidentiality") == "HIGH"
    assert canonical_risk_for("notice_periods") == "MEDIUM"
    assert canonical_risk_for("force_majeure") == "MEDIUM"
    assert canonical_risk_for("ambiguous_clause") == "LOW"

    # Unknown topic falls back to LOW.
    assert canonical_risk_for("blockchain_custody") == "LOW"


def test_rubric_canonical_conflicts_on_matching_topic():
    from eval.rubric_audit import rubric_canonical_conflicts  # noqa: PLC0415
    from eval.schemas import Clause  # noqa: PLC0415

    company = [
        Clause(
            section="7.1",
            text="The liability cap shall not exceed twelve months of fees.",
            party="company",
            canonical_topic="liability_cap",
        ),
    ]
    vendor = [
        Clause(
            section="9.2",
            text="Total damages capped at thirty thousand dollars.",
            party="vendor",
            canonical_topic="liability_cap",
        ),
    ]
    conflicts = rubric_canonical_conflicts(company, vendor)
    assert len(conflicts) == 1
    assert conflicts[0].canonical_topic == "liability_cap"
    assert conflicts[0].canonical_risk == "CRITICAL"
    assert conflicts[0].canonical_favor == "Company"
    assert conflicts[0].company_section == "7.1"
    assert conflicts[0].vendor_section == "9.2"


def test_rubric_canonical_conflicts_on_disjoint_topics():
    from eval.rubric_audit import rubric_canonical_conflicts  # noqa: PLC0415
    from eval.schemas import Clause  # noqa: PLC0415

    # Different topics — should produce zero canonical conflicts per Rule 3.
    company = [
        Clause(
            section="7.1",
            text="Liability cap of twelve months fees.",
            party="company",
            canonical_topic="liability_cap",
        ),
    ]
    vendor = [
        Clause(
            section="11.4",
            text="Force majeure events excuse performance.",
            party="vendor",
            canonical_topic="force_majeure",
        ),
    ]
    assert rubric_canonical_conflicts(company, vendor) == []


def test_rubric_canonical_conflicts_with_favor_override():
    from eval.rubric_audit import rubric_canonical_conflicts  # noqa: PLC0415
    from eval.schemas import Clause  # noqa: PLC0415

    company = [
        Clause(
            section="6.0",
            text="Payment due net 30 days from invoice.",
            party="company",
            canonical_topic="payment_terms",
        ),
    ]
    vendor = [
        Clause(
            section="8.0",
            text="Payment due net 90 days from invoice.",
            party="vendor",
            canonical_topic="payment_terms",
        ),
    ]
    # If the company is the payer, vendor's longer net-90 favors the company.
    conflicts = rubric_canonical_conflicts(
        company, vendor, favor_overrides={"payment_terms": "Vendor"}
    )
    assert len(conflicts) == 1
    assert conflicts[0].canonical_favor == "Vendor"


# ---------------------------------------------------------------------------
# Pydantic schemas — basic validation
# ---------------------------------------------------------------------------


def test_scenario_validation_clear_no_conflict_must_be_empty():
    import pytest  # noqa: PLC0415
    from pydantic import ValidationError  # noqa: PLC0415
    from eval.schemas import Scenario  # noqa: PLC0415

    with pytest.raises(ValidationError):
        Scenario(
            id="clear_no_conflict_001",
            tier="clear_no_conflict",
            description="A clear-no-conflict scenario test fixture.",
            company_clauses=[{"section": "1", "text": "foo", "party": "company"}],
            vendor_clauses=[{"section": "1", "text": "foo", "party": "vendor"}],
            expected_conflicts=[
                {
                    "topic": "Liability cap",
                    "canonical_risk": "CRITICAL",
                    "canonical_favor": "Company",
                }
            ],
            expected_total_conflicts=1,
        )


def test_scenario_validation_clear_conflict_must_have_at_least_one():
    import pytest  # noqa: PLC0415
    from pydantic import ValidationError  # noqa: PLC0415
    from eval.schemas import Scenario  # noqa: PLC0415

    with pytest.raises(ValidationError):
        Scenario(
            id="clear_conflict_001",
            tier="clear_conflict",
            description="A clear-conflict scenario without any expected conflicts.",
            company_clauses=[{"section": "1", "text": "foo", "party": "company"}],
            vendor_clauses=[{"section": "1", "text": "foo", "party": "vendor"}],
            expected_conflicts=[],
            expected_total_conflicts=0,
        )


def test_expected_conflict_acceptable_sets_default_to_singletons():
    from eval.schemas import ExpectedConflict  # noqa: PLC0415

    ec = ExpectedConflict(
        topic="Liability cap",
        canonical_risk="CRITICAL",
        canonical_favor="Company",
    )
    assert ec.acceptable_topics == ["Liability cap"]
    assert ec.acceptable_risks == ["CRITICAL"]
    assert ec.acceptable_favors == ["Company"]


def test_conflict_count_range_rejects_inverted_order():
    import pytest  # noqa: PLC0415
    from pydantic import ValidationError  # noqa: PLC0415
    from eval.schemas import ConflictCountRange  # noqa: PLC0415

    with pytest.raises(ValidationError):
        ConflictCountRange(min=5, max=2)


# ---------------------------------------------------------------------------
# Prompt mirror — drift detection (light Day-1 version)
# ---------------------------------------------------------------------------


def test_eval_full_prompt_contains_production_core():
    from eval.prompts import (  # noqa: PLC0415
        SYSTEM_PROMPT_FULL_EVAL,
        SYSTEM_PROMPT_PRODUCTION,
    )

    # FULL is production + eval-mode suffix.
    assert SYSTEM_PROMPT_PRODUCTION in SYSTEM_PROMPT_FULL_EVAL
    assert "EVAL MODE" in SYSTEM_PROMPT_FULL_EVAL


def test_stripped_prompt_demands_json_only():
    from eval.prompts import SYSTEM_PROMPT_STRIPPED  # noqa: PLC0415

    assert "JSON only" in SYSTEM_PROMPT_STRIPPED
    assert "No tools" in SYSTEM_PROMPT_STRIPPED


def test_render_stripped_user_message_wraps_xml():
    from eval.prompts import render_stripped_user_message  # noqa: PLC0415

    rendered = render_stripped_user_message(
        company_clauses=[{"section": "1", "text": "foo"}],
        vendor_clauses=[{"section": "2", "text": "bar"}],
    )
    assert "<company_terms>" in rendered
    assert "<vendor_terms>" in rendered
    assert "foo" in rendered
    assert "bar" in rendered


# ---------------------------------------------------------------------------
# Runners CLI — Day-1 status message
# ---------------------------------------------------------------------------


def test_runners_cli_dry_mode_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "eval.runners", "--mode", "dry"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    # --mode dry prints status and exits non-zero (intentional, all days).
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    # Accept any day-status banner — message evolves Day 1 → Day 6 → Day 8.
    assert any(
        marker in combined
        for marker in ("Day 1", "Day-1", "Day 6", "Day-6", "Day 8", "Day-8",
                       "status", "eval harness")
    ), combined
