"""Mock-based runner tests. Zero LLM calls, CI-safe.

Verifies that FULL and STRIPPED pipelines:
- Make the expected number of API calls per scenario.
- Pass the right system prompt to each branch.
- Mock extract_clauses correctly per party_label.
- Capture conflicts from generate_redline_brief (FULL) or JSON output (STRIPPED).
- Record CallTraces with cost/duration.
- Handle malformed output gracefully (no crash, error captured in result).
- Drift-detection: TOOLS_FOR_EVAL mirrors backend/tools.py TOOLS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers — build fake Anthropic Messages API responses
# ---------------------------------------------------------------------------


def _fake_response(
    stop_reason: str,
    content_blocks: list,
    input_tokens: int = 1000,
    output_tokens: int = 500,
):
    """Construct a fake response object shaped like Anthropic's SDK."""
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content_blocks,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def _tool_use_block(tool_use_id: str, name: str, tool_input: dict):
    return SimpleNamespace(
        type="tool_use",
        id=tool_use_id,
        name=name,
        input=tool_input,
    )


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _make_minimal_scenario():
    from eval.schemas import Scenario  # noqa: PLC0415

    return Scenario(
        id="clear_conflict_001",
        tier="clear_conflict",
        description="Minimal test scenario fixture.",
        company_clauses=[
            {
                "section": "7.1",
                "text": "Liability capped at 12 months of fees.",
                "party": "company",
                "canonical_topic": "liability_cap",
            }
        ],
        vendor_clauses=[
            {
                "section": "9.2",
                "text": "Liability capped at $30,000.",
                "party": "vendor",
                "canonical_topic": "liability_cap",
            }
        ],
        expected_conflicts=[
            {
                "topic": "Liability cap",
                "canonical_risk": "CRITICAL",
                "canonical_favor": "Company",
                "gold_company_section": "7.1",
                "gold_vendor_section": "9.2",
            }
        ],
        expected_total_conflicts=1,
    )


# ---------------------------------------------------------------------------
# Mocked tool tests
# ---------------------------------------------------------------------------


def test_mock_extract_clauses_company():
    from eval.runners import _mock_extract_clauses  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    result = _mock_extract_clauses(scenario, "company")
    assert result["success"] is True
    assert result["party"] == "company"
    assert result["clause_count"] == 1
    assert result["clauses"][0]["section"] == "7.1"


def test_mock_extract_clauses_vendor():
    from eval.runners import _mock_extract_clauses  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    result = _mock_extract_clauses(scenario, "vendor")
    assert result["success"] is True
    assert result["party"] == "vendor"
    assert result["clauses"][0]["section"] == "9.2"


def test_mock_extract_clauses_unknown_label():
    from eval.runners import _mock_extract_clauses  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    result = _mock_extract_clauses(scenario, "unknown_party")
    assert result["success"] is False
    assert "Unknown party_label" in result["error"]


def test_mock_generate_redline_brief_counts_summary():
    from eval.runners import _mock_generate_redline_brief  # noqa: PLC0415

    def full(risk, topic):
        return {
            "risk": risk, "topic": topic, "company_section": "1", "company_text": "company language",
            "vendor_section": "2", "vendor_text": "vendor language",
            "conflict_explanation": "materially different obligations", "favor": "Company",
            "resolution": "use the company language as the starting point",
        }

    conflicts = [
        full("CRITICAL", "Liability cap"),
        full("HIGH", "Payment terms"),
        full("high", "Confidentiality"),  # lowercase ok: validator upper-cases
    ]
    result = _mock_generate_redline_brief(conflicts)
    assert result["success"] is True
    assert result["report"]["total_conflicts"] == 3
    assert result["report"]["summary"]["CRITICAL"] == 1
    assert result["report"]["summary"]["HIGH"] == 2


def test_mock_generate_redline_brief_rejects_partial_conflicts():
    """The eval runs the production validator: a conflict missing required
    fields is returned as a schema error for the model to repair, exactly
    as in production."""
    from eval.runners import _mock_generate_redline_brief  # noqa: PLC0415

    result = _mock_generate_redline_brief([{"risk": "CRITICAL", "topic": "Liability cap"}])
    assert result["success"] is False
    assert result["validation_errors"]
    assert "company_section" in result["validation_errors"][0]


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def test_parse_json_safe_plain():
    from eval.runners import _parse_json_safe  # noqa: PLC0415

    assert _parse_json_safe('{"a": 1, "b": [1,2,3]}') == {"a": 1, "b": [1, 2, 3]}


def test_parse_json_safe_markdown_fence():
    from eval.runners import _parse_json_safe  # noqa: PLC0415

    out = _parse_json_safe('```json\n{"a": 1}\n```')
    assert out == {"a": 1}


def test_parse_json_safe_prose_prelude():
    from eval.runners import _parse_json_safe  # noqa: PLC0415

    out = _parse_json_safe(
        'Sure! Here is the JSON:\n{"a": 1, "b": 2}\nLet me know if you need more.'
    )
    assert out == {"a": 1, "b": 2}


def test_parse_json_safe_empty_returns_empty():
    from eval.runners import _parse_json_safe  # noqa: PLC0415

    assert _parse_json_safe("") == {}
    assert _parse_json_safe("complete garbage no braces") == {}


# ---------------------------------------------------------------------------
# Conflict coercion
# ---------------------------------------------------------------------------


def test_coerce_conflicts_fills_missing_id():
    from eval.runners import _coerce_conflicts  # noqa: PLC0415

    raw = [
        {
            "risk": "CRITICAL",
            "topic": "Liability cap",
            "company_section": "7.1",
            "company_text": "12 months fees",
            "vendor_section": "9.2",
            "vendor_text": "$30K",
            "conflict_explanation": "Material gap",
            "favor": "Company",
            "resolution": "Use company language",
        }
    ]
    out = _coerce_conflicts(raw)
    assert len(out) == 1
    assert out[0].id == 1
    assert out[0].risk == "CRITICAL"


def test_coerce_conflicts_skips_malformed():
    from eval.runners import _coerce_conflicts  # noqa: PLC0415

    raw = [
        {"this is not a conflict": True},
        "not even a dict",
        {
            "id": 99,
            "risk": "HIGH",
            "topic": "Payment",
            "company_section": "5",
            "company_text": "Net 30",
            "vendor_section": "8",
            "vendor_text": "Net 90",
            "conflict_explanation": "x",
            "favor": "Vendor",
            "resolution": "y",
        },
    ]
    out = _coerce_conflicts(raw)
    assert len(out) == 1
    assert out[0].id == 99


# ---------------------------------------------------------------------------
# FULL pipeline — mocked end-to-end
# ---------------------------------------------------------------------------


def test_run_full_pipeline_three_turns():
    """Standard FULL pipeline: extract A, extract B, generate brief, end_turn."""
    from eval.runners import run_full_pipeline  # noqa: PLC0415

    scenario = _make_minimal_scenario()

    # Turn 1: agent calls extract_clauses for company.
    # Turn 2: agent calls extract_clauses for vendor.
    # Turn 3: agent calls generate_redline_brief.
    # Turn 4: end_turn.
    responses = [
        _fake_response(
            stop_reason="tool_use",
            content_blocks=[
                _tool_use_block(
                    "tu_1",
                    "extract_clauses",
                    {"pdf_path": "scenario://x/company", "party_label": "company"},
                )
            ],
        ),
        _fake_response(
            stop_reason="tool_use",
            content_blocks=[
                _tool_use_block(
                    "tu_2",
                    "extract_clauses",
                    {"pdf_path": "scenario://x/vendor", "party_label": "vendor"},
                )
            ],
        ),
        _fake_response(
            stop_reason="tool_use",
            content_blocks=[
                _tool_use_block(
                    "tu_3",
                    "generate_redline_brief",
                    {
                        "conflicts": [
                            {
                                "id": 1,
                                "risk": "CRITICAL",
                                "topic": "Liability cap",
                                "company_section": "7.1",
                                "company_text": "12 months fees",
                                "vendor_section": "9.2",
                                "vendor_text": "$30K",
                                "conflict_explanation": "Material gap",
                                "favor": "Company",
                                "resolution": "Use company language",
                            }
                        ],
                        "output_format": "json",
                    },
                )
            ],
        ),
        _fake_response(
            stop_reason="end_turn",
            content_blocks=[_text_block("Analysis complete.")],
        ),
    ]
    client = MagicMock()
    client.messages.create.side_effect = responses

    traces = []
    with patch("eval.runners._get_anthropic_client", return_value=client):
        result = run_full_pipeline(
            scenario, rep=0, on_trace=traces.append
        )

    assert client.messages.create.call_count == 4
    assert result.error is None
    assert result.predicted_total == 1
    assert result.predicted_conflicts is not None
    assert len(result.predicted_conflicts) == 1
    assert result.predicted_conflicts[0].risk == "CRITICAL"
    assert result.branch == "full"
    assert len(traces) == 4
    assert traces[0].branch == "full"
    assert traces[0].scenario_id == scenario.id


def test_run_full_pipeline_passes_eval_system_prompt():
    """Drift check: FULL pipeline must use SYSTEM_PROMPT_FULL_EVAL."""
    from eval.runners import run_full_pipeline  # noqa: PLC0415
    from eval.prompts import SYSTEM_PROMPT_FULL_EVAL  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    responses = [
        _fake_response("end_turn", [_text_block("done")]),
    ]
    client = MagicMock()
    client.messages.create.side_effect = responses

    with patch("eval.runners._get_anthropic_client", return_value=client):
        run_full_pipeline(scenario, rep=0)

    system = client.messages.create.call_args.kwargs["system"]
    # The prompt is sent as a cache_control block so repeated runs reuse the prefix.
    assert isinstance(system, list) and system[0]["text"] == SYSTEM_PROMPT_FULL_EVAL
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_run_full_pipeline_captures_api_error():
    """API error should populate result.error rather than crash."""
    from eval.runners import run_full_pipeline  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("simulated 500")

    with patch("eval.runners._get_anthropic_client", return_value=client):
        result = run_full_pipeline(scenario, rep=0)

    assert result.error is not None
    assert "simulated 500" in result.error
    assert result.predicted_conflicts is None


def test_run_full_pipeline_max_turns_recorded():
    """If the agent never calls end_turn, error reflects the max-turns cap."""
    from eval.runners import run_full_pipeline  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    # Forever loop calling extract_clauses(company).
    response = _fake_response(
        stop_reason="tool_use",
        content_blocks=[
            _tool_use_block(
                "tu_loop",
                "extract_clauses",
                {"pdf_path": "x", "party_label": "company"},
            )
        ],
    )
    client = MagicMock()
    client.messages.create.return_value = response

    with patch("eval.runners._get_anthropic_client", return_value=client):
        result = run_full_pipeline(scenario, rep=0)

    assert result.error is not None
    assert "Max turns" in result.error


# ---------------------------------------------------------------------------
# STRIPPED pipeline — mocked
# ---------------------------------------------------------------------------


def test_run_stripped_pipeline_one_call():
    """STRIPPED pipeline makes exactly one LLM call."""
    from eval.runners import run_stripped_pipeline  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    json_out = json.dumps(
        {
            "conflicts": [
                {
                    "id": 1,
                    "risk": "CRITICAL",
                    "topic": "Liability cap",
                    "company_section": "7.1",
                    "company_text": "12 months",
                    "vendor_section": "9.2",
                    "vendor_text": "$30K",
                    "conflict_explanation": "Gap",
                    "favor": "Company",
                    "resolution": "Use company",
                }
            ],
            "total_conflicts": 1,
        }
    )
    response = _fake_response("end_turn", [_text_block(json_out)])
    client = MagicMock()
    client.messages.create.return_value = response

    traces = []
    with patch("eval.runners._get_anthropic_client", return_value=client):
        result = run_stripped_pipeline(
            scenario, rep=0, on_trace=traces.append
        )

    assert client.messages.create.call_count == 1
    assert result.error is None
    assert result.predicted_total == 1
    assert result.predicted_conflicts is not None
    assert result.predicted_conflicts[0].risk == "CRITICAL"
    assert result.branch == "stripped"
    assert len(traces) == 1
    assert traces[0].role == "stripped"


def test_run_stripped_pipeline_passes_stripped_system_prompt():
    """Drift check: STRIPPED pipeline must use SYSTEM_PROMPT_STRIPPED."""
    from eval.runners import run_stripped_pipeline  # noqa: PLC0415
    from eval.prompts import SYSTEM_PROMPT_STRIPPED  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    response = _fake_response(
        "end_turn", [_text_block('{"conflicts": [], "total_conflicts": 0}')]
    )
    client = MagicMock()
    client.messages.create.return_value = response

    with patch("eval.runners._get_anthropic_client", return_value=client):
        run_stripped_pipeline(scenario, rep=0)

    assert client.messages.create.call_args.kwargs["system"] == SYSTEM_PROMPT_STRIPPED


def test_run_stripped_pipeline_malformed_json_no_crash():
    """Malformed JSON output: result.predicted_total falls back to 0."""
    from eval.runners import run_stripped_pipeline  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    response = _fake_response("end_turn", [_text_block("not even close to JSON")])
    client = MagicMock()
    client.messages.create.return_value = response

    with patch("eval.runners._get_anthropic_client", return_value=client):
        result = run_stripped_pipeline(scenario, rep=0)

    assert result.error is None
    assert result.predicted_total == 0
    # predicted_conflicts may be empty list or None.
    assert not result.predicted_conflicts


def test_run_stripped_pipeline_captures_api_error():
    from eval.runners import run_stripped_pipeline  # noqa: PLC0415

    scenario = _make_minimal_scenario()
    client = MagicMock()
    client.messages.create.side_effect = TimeoutError("simulated timeout")

    with patch("eval.runners._get_anthropic_client", return_value=client):
        result = run_stripped_pipeline(scenario, rep=0)

    assert result.error is not None
    assert "simulated timeout" in result.error


# ---------------------------------------------------------------------------
# Drift detection — TOOLS_FOR_EVAL must mirror backend/tools.py
# ---------------------------------------------------------------------------


def test_tools_for_eval_mirrors_backend():
    """TOOLS_FOR_EVAL must stay in sync with backend/tools.py TOOLS schema.

    Imports backend.tools without triggering ANTHROPIC_API_KEY validation
    by stubbing fitz first.
    """
    from eval.runners import TOOLS_FOR_EVAL  # noqa: PLC0415

    # Stub fitz to avoid the real PyMuPDF import; we only need TOOLS metadata.
    sys.modules.setdefault("fitz", MagicMock())
    # Stub config to avoid ANTHROPIC_API_KEY validation at import.
    if "config" not in sys.modules:
        cfg = MagicMock()
        cfg.RISK_LEVELS = {}
        cfg.MAX_CLAUSES = 120
        sys.modules["config"] = cfg

    try:
        from backend.tools import TOOLS as PRODUCTION_TOOLS  # noqa: PLC0415
    except Exception as exc:
        pytest.skip(f"Cannot import backend.tools for drift check: {exc}")

    eval_names = {t["name"] for t in TOOLS_FOR_EVAL}
    prod_names = {t["name"] for t in PRODUCTION_TOOLS}
    assert eval_names == prod_names, (
        f"Tool names drift: eval has {eval_names}, prod has {prod_names}. "
        f"Update TOOLS_FOR_EVAL in eval/runners.py."
    )
    # Required-fields-per-tool drift check.
    for prod_tool in PRODUCTION_TOOLS:
        eval_tool = next(t for t in TOOLS_FOR_EVAL if t["name"] == prod_tool["name"])
        prod_required = set(prod_tool["input_schema"].get("required", []))
        eval_required = set(eval_tool["input_schema"].get("required", []))
        assert prod_required == eval_required, (
            f"Tool '{prod_tool['name']}' required-fields drift: "
            f"prod={prod_required}, eval={eval_required}."
        )
