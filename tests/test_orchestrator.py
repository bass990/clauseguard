"""Mock-based orchestrator tests. Zero LLM calls, CI-safe.

Verifies that the orchestrator:
- Runs (scenario × branch × rep) Cartesian product correctly.
- Captures pipeline errors without crashing.
- Aggregates costs via the trace callback chain.
- Produces a report with the headline, branch tables, lift table, per-tier
  breakdown, per-scenario detail, cost totals, and methodology footer.
- Writes the report + JSON snapshot to disk on save_run.
- The default eval-small scenario set spans all 5 tiers and includes
  adversarial_001 (the prompt-injection test).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _fake_response(
    stop_reason: str,
    content_blocks: list,
    input_tokens: int = 800,
    output_tokens: int = 400,
):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content_blocks,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tu_id: str, name: str, tool_input: dict):
    return SimpleNamespace(
        type="tool_use", id=tu_id, name=name, input=tool_input
    )


def _stripped_canned_response_one_critical():
    payload = {
        "conflicts": [
            {
                "id": 1,
                "risk": "CRITICAL",
                "topic": "Liability cap",
                "company_section": "7.1",
                "company_text": "12 months fees",
                "vendor_section": "9.2",
                "vendor_text": "$30,000",
                "conflict_explanation": "Material",
                "favor": "Company",
                "resolution": "Use company",
            }
        ],
        "total_conflicts": 1,
    }
    return _fake_response("end_turn", [_text_block(json.dumps(payload))])


def _stripped_canned_response_no_conflicts():
    payload = {"conflicts": [], "total_conflicts": 0}
    return _fake_response("end_turn", [_text_block(json.dumps(payload))])


def _full_canned_responses_one_critical():
    """Three-turn FULL response: extract A, extract B, redline, end_turn."""
    return [
        _fake_response(
            "tool_use",
            [_tool_use_block(
                "tu1", "extract_clauses",
                {"pdf_path": "x", "party_label": "company"},
            )],
        ),
        _fake_response(
            "tool_use",
            [_tool_use_block(
                "tu2", "extract_clauses",
                {"pdf_path": "x", "party_label": "vendor"},
            )],
        ),
        _fake_response(
            "tool_use",
            [_tool_use_block(
                "tu3", "generate_redline_brief",
                {
                    "conflicts": [
                        {
                            "id": 1,
                            "risk": "CRITICAL",
                            "topic": "Liability cap",
                            "company_section": "7.1",
                            "company_text": "x",
                            "vendor_section": "9.2",
                            "vendor_text": "y",
                            "conflict_explanation": "z",
                            "favor": "Company",
                            "resolution": "w",
                        }
                    ],
                    "output_format": "json",
                },
            )],
        ),
        _fake_response("end_turn", [_text_block("done")]),
    ]


def _full_canned_responses_no_conflicts():
    return [
        _fake_response(
            "tool_use",
            [_tool_use_block(
                "tu1", "extract_clauses",
                {"pdf_path": "x", "party_label": "company"},
            )],
        ),
        _fake_response(
            "tool_use",
            [_tool_use_block(
                "tu2", "extract_clauses",
                {"pdf_path": "x", "party_label": "vendor"},
            )],
        ),
        _fake_response(
            "tool_use",
            [_tool_use_block(
                "tu3", "generate_redline_brief",
                {"conflicts": [], "output_format": "json"},
            )],
        ),
        _fake_response("end_turn", [_text_block("no conflicts")]),
    ]


# ---------------------------------------------------------------------------
# Default eval-small scenario set
# ---------------------------------------------------------------------------


def test_default_eval_small_spans_all_tiers():
    from eval.orchestrator import DEFAULT_EVAL_SMALL_SCENARIO_IDS  # noqa: PLC0415

    tier_prefixes = {
        "clear_conflict_": False,
        "clear_no_conflict_": False,
        "ambiguous_": False,
        "severity_tiering_": False,
        "adversarial_": False,
    }
    for sid in DEFAULT_EVAL_SMALL_SCENARIO_IDS:
        for prefix in tier_prefixes:
            if sid.startswith(prefix):
                tier_prefixes[prefix] = True
                break
    assert all(tier_prefixes.values()), (
        f"DEFAULT_EVAL_SMALL_SCENARIO_IDS does not span all tiers: {tier_prefixes}"
    )


def test_default_eval_small_includes_prompt_injection():
    """Adversarial_001 is the prompt-injection test — highest-value scenario.

    Mirrors ChainPilot's discipline of forcing the highest-leverage adversarial
    test into the small eval set."""
    from eval.orchestrator import DEFAULT_EVAL_SMALL_SCENARIO_IDS  # noqa: PLC0415

    assert "adversarial_001" in DEFAULT_EVAL_SMALL_SCENARIO_IDS


def test_default_eval_small_scenarios_exist_on_disk():
    """Every default eval-small scenario id must have a JSON file."""
    from eval.orchestrator import DEFAULT_EVAL_SMALL_SCENARIO_IDS  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    for sid in DEFAULT_EVAL_SMALL_SCENARIO_IDS:
        assert (scenarios_dir / f"{sid}.json").exists(), (
            f"DEFAULT_EVAL_SMALL_SCENARIO_IDS includes '{sid}' but "
            f"eval/scenarios/{sid}.json does not exist."
        )


# ---------------------------------------------------------------------------
# run_eval — Cartesian product
# ---------------------------------------------------------------------------


def test_run_eval_runs_cartesian_product():
    """1 scenario × 2 branches × 2 reps = 4 results."""
    from eval.orchestrator import run_eval  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"

    # Build response queues for the API calls.
    full_responses_per_rep = _full_canned_responses_one_critical()
    stripped_response_per_rep = _stripped_canned_response_one_critical()
    # 2 reps × (4 full turns + 1 stripped turn) = 10 responses needed.
    full_queue = full_responses_per_rep * 2 + [stripped_response_per_rep] * 2

    client = MagicMock()
    client.messages.create.side_effect = full_queue

    with patch("eval.runners._get_anthropic_client", return_value=client):
        results = run_eval(
            scenario_ids=["clear_conflict_001"],
            branches=["full", "stripped"],
            n_reps=2,
            scenarios_dir=scenarios_dir,
        )

    assert len(results) == 4
    branches = [r.branch for r in results]
    assert branches.count("full") == 2
    assert branches.count("stripped") == 2


def test_run_eval_handles_pipeline_error_gracefully():
    """Errored scenario should record error, not crash."""
    from eval.orchestrator import run_eval  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("simulated API outage")

    with patch("eval.runners._get_anthropic_client", return_value=client):
        results = run_eval(
            scenario_ids=["clear_conflict_001"],
            branches=["full"],
            n_reps=1,
            scenarios_dir=scenarios_dir,
        )
    assert len(results) == 1
    assert results[0].error is not None
    assert "simulated API outage" in results[0].error


def test_run_eval_missing_scenario_file_reports_error():
    from eval.orchestrator import run_eval  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    results = run_eval(
        scenario_ids=["does_not_exist_999"],
        branches=["full"],
        n_reps=1,
        scenarios_dir=scenarios_dir,
    )
    assert len(results) == 1
    assert results[0].error is not None
    assert "not found" in results[0].error.lower()


# ---------------------------------------------------------------------------
# run_and_save — end-to-end
# ---------------------------------------------------------------------------


def test_run_and_save_writes_report_and_snapshot(tmp_path):
    """End-to-end: run eval, render report, save to disk."""
    from eval.orchestrator import run_and_save  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    reports_dir = tmp_path / "reports"

    full_responses = _full_canned_responses_one_critical()
    stripped_responses = [_stripped_canned_response_one_critical()]
    queue = full_responses + stripped_responses

    client = MagicMock()
    client.messages.create.side_effect = queue

    with patch("eval.runners._get_anthropic_client", return_value=client):
        md_path, json_path, report_text = run_and_save(
            scenario_ids=["clear_conflict_001"],
            branches=["full", "stripped"],
            n_reps=1,
            scenarios_dir=scenarios_dir,
            reports_dir=reports_dir,
        )

    assert md_path.exists()
    assert json_path.exists()
    assert json_path.name == "latest_run.json"

    # Report content sanity checks.
    assert "ClauseGuard Eval Report" in report_text
    assert "## Headline" in report_text
    assert "Branch `full`" in report_text or "Branch `stripped`" in report_text
    assert "Per-scenario detail" in report_text
    assert "Cost & latency" in report_text
    assert "Methodology disclosure" in report_text

    # Snapshot JSON sanity.
    snap = json.loads(json_path.read_text(encoding="utf-8"))
    assert snap["scenario_ids"] == ["clear_conflict_001"]
    assert snap["n_reps"] == 1
    assert "results" in snap
    assert "branch_metrics" in snap
    assert "lifts" in snap


def test_run_and_save_report_headline_reflects_lift(tmp_path):
    """If full pipeline catches a conflict and stripped does not,
    the headline interpretation should be 'full_wins' framing."""
    from eval.orchestrator import run_and_save  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    reports_dir = tmp_path / "reports"

    full_responses = _full_canned_responses_one_critical()
    stripped_responses = [_stripped_canned_response_no_conflicts()]
    queue = full_responses + stripped_responses

    client = MagicMock()
    client.messages.create.side_effect = queue

    with patch("eval.runners._get_anthropic_client", return_value=client):
        _, _, report_text = run_and_save(
            scenario_ids=["clear_conflict_001"],
            branches=["full", "stripped"],
            n_reps=1,
            scenarios_dir=scenarios_dir,
            reports_dir=reports_dir,
        )

    # Either full_wins or it's at least not stripped_wins.
    assert "FULL pipeline beats STRIPPED" in report_text or "FULL ≈ STRIPPED" in report_text


def test_run_and_save_report_headline_stripped_wins(tmp_path):
    """Inverse: full misses, stripped catches → headline should call out stripped."""
    from eval.orchestrator import run_and_save  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    reports_dir = tmp_path / "reports"

    full_responses = _full_canned_responses_no_conflicts()
    stripped_responses = [_stripped_canned_response_one_critical()]
    queue = full_responses + stripped_responses

    client = MagicMock()
    client.messages.create.side_effect = queue

    with patch("eval.runners._get_anthropic_client", return_value=client):
        _, _, report_text = run_and_save(
            scenario_ids=["clear_conflict_001"],
            branches=["full", "stripped"],
            n_reps=1,
            scenarios_dir=scenarios_dir,
            reports_dir=reports_dir,
        )

    assert "STRIPPED single-prompt baseline beats FULL" in report_text


# ---------------------------------------------------------------------------
# Cost aggregation
# ---------------------------------------------------------------------------


def test_run_and_save_aggregates_cost(tmp_path):
    """Cost totals in the report should be non-zero after real calls."""
    from eval.orchestrator import run_and_save  # noqa: PLC0415

    scenarios_dir = REPO_ROOT / "eval" / "scenarios"
    reports_dir = tmp_path / "reports"

    queue = _full_canned_responses_one_critical() + [_stripped_canned_response_one_critical()]
    client = MagicMock()
    client.messages.create.side_effect = queue

    with patch("eval.runners._get_anthropic_client", return_value=client):
        _, json_path, report_text = run_and_save(
            scenario_ids=["clear_conflict_001"],
            branches=["full", "stripped"],
            n_reps=1,
            scenarios_dir=scenarios_dir,
            reports_dir=reports_dir,
        )

    snap = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(snap["traces"]) == 5  # 4 full turns + 1 stripped
    total_cost = sum(t["cost_usd"] for t in snap["traces"])
    assert total_cost > 0.0
    assert "Total cost" in report_text
