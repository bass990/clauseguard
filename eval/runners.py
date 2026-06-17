"""FULL and STRIPPED pipeline runners. Day-6 implementation.

FULL branch: mirrors clauseguard/backend/agent.py — agent loop with tool_use,
but extract_clauses is MOCKED to return scenario.company_clauses /
vendor_clauses (the PDF parsing step is bypassed; we're testing reasoning).
generate_redline_brief captures the agent's conflict list.

STRIPPED branch: one LLM call with both clause arrays inline as XML in the
user message. Returns parsed conflicts directly. No tools.

Both pipelines return a ScenarioResult that the orchestrator collects and
the scorers consume.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from eval.instrumentation import CallTrace, make_trace
from eval.prompts import (
    SYSTEM_PROMPT_FULL_EVAL,
    SYSTEM_PROMPT_STRIPPED,
    render_stripped_user_message,
)
from eval.schemas import PredictedConflict, Scenario, ScenarioResult


# Anthropic client is loaded lazily so tests can patch it without requiring
# a real API key at import time.
_ANTHROPIC_CLIENT = None


def _get_anthropic_client():
    """Lazy-load the Anthropic client. Patched in tests."""
    global _ANTHROPIC_CLIENT
    if _ANTHROPIC_CLIENT is None:
        import anthropic  # noqa: PLC0415
        _ANTHROPIC_CLIENT = anthropic.Anthropic()
    return _ANTHROPIC_CLIENT


# Tool schemas for the FULL branch — mirrored from backend/tools.py TOOLS.
# A drift-detection test in test_runners.py keeps these in sync.
TOOLS_FOR_EVAL: list[dict] = [
    {
        "name": "extract_clauses",
        "description": (
            "Parse a contract PDF file and extract all clauses with their "
            "section numbers and text. Call this once for each contract "
            "before comparing them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the PDF file",
                },
                "party_label": {
                    "type": "string",
                    "description": (
                        "Label for this contract party: 'company' or 'vendor'"
                    ),
                },
            },
            "required": ["pdf_path", "party_label"],
        },
    },
    {
        "name": "generate_redline_brief",
        "description": (
            "Compile all identified conflicts into a final structured "
            "redline brief. Call this as the last step after all conflicts "
            "have been identified and assessed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conflicts": {
                    "type": "array",
                    "description": (
                        "Array of conflict objects with the 10 fields from "
                        "the system prompt schema."
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                },
            },
            "required": ["conflicts", "output_format"],
        },
    },
]


# ---------------------------------------------------------------------------
# Scenario IO
# ---------------------------------------------------------------------------


def load_scenario(scenario_path: Path) -> Scenario:
    """Load and validate one scenario JSON file."""
    with scenario_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return Scenario(**data)


def list_scenarios(scenarios_dir: Path) -> list[Scenario]:
    """Load all scenarios from a directory, sorted by id."""
    paths = sorted(scenarios_dir.glob("*.json"))
    return [load_scenario(p) for p in paths]


def _parse_json_safe(text: str) -> dict[str, Any]:
    """Extract a JSON object from possibly-prosey LLM output."""
    if not text:
        return {}

    stripped = text.strip()
    for fence in ("```json", "```JSON", "```"):
        if stripped.startswith(fence):
            stripped = stripped[len(fence):].lstrip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        try:
            return json.loads(stripped[first:last + 1])
        except json.JSONDecodeError:
            pass

    return {}


def _coerce_conflicts(
    raw_conflicts: list[Any],
) -> list[PredictedConflict]:
    """Coerce a list of raw conflict dicts into PredictedConflict objects.

    Skips entries that don't validate rather than failing the whole run —
    a malformed conflict shouldn't lose the rest of the agent's findings.
    """
    out: list[PredictedConflict] = []
    for i, raw in enumerate(raw_conflicts):
        if not isinstance(raw, dict):
            continue
        # Fill in id if missing; production schema requires it.
        if "id" not in raw:
            raw = dict(raw)
            raw["id"] = i + 1
        try:
            out.append(PredictedConflict(**raw))
        except Exception:
            # Skip malformed; the orchestrator's report will surface the gap
            # via predicted vs expected counts.
            continue
    return out


# ---------------------------------------------------------------------------
# Mocked tool implementations (FULL branch)
# ---------------------------------------------------------------------------


def _mock_extract_clauses(
    scenario: Scenario,
    party_label: str,
) -> dict[str, Any]:
    """Return scenario clauses for the requested party_label."""
    label = (party_label or "").lower().strip()
    if label == "company":
        clauses = scenario.company_clauses
    elif label == "vendor":
        clauses = scenario.vendor_clauses
    else:
        return {
            "success": False,
            "error": f"Unknown party_label: '{party_label}'",
            "party": party_label,
            "clauses": [],
        }
    serialized = [
        {"section": c.section, "text": c.text, "party": c.party}
        for c in clauses
    ]
    return {
        "success": True,
        "party": label,
        "clause_count": len(serialized),
        "total_found": len(serialized),
        "truncated": False,
        "clauses": serialized,
    }


def _mock_generate_redline_brief(
    conflicts: list[Any],
) -> dict[str, Any]:
    """Capture the agent's conflicts list. Same shape as production."""
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for c in conflicts or []:
        if isinstance(c, dict):
            risk = str(c.get("risk", "LOW")).upper()
            if risk in summary:
                summary[risk] += 1
    return {
        "success": True,
        "report": {
            "title": "Contract Conflict Analysis — Redline Brief",
            "total_conflicts": len(conflicts or []),
            "summary": summary,
            "conflicts": conflicts or [],
        },
    }


# ---------------------------------------------------------------------------
# FULL branch
# ---------------------------------------------------------------------------


MAX_TURNS = 20
DEFAULT_MAX_TOKENS = 4096


def _call_llm_full(
    client,
    model: str,
    messages: list[dict],
    max_tokens: int,
):
    """One Messages API call for the FULL agent loop."""
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT_FULL_EVAL,
        tools=TOOLS_FOR_EVAL,
        messages=messages,
    )


def _call_llm_stripped(
    client,
    model: str,
    user_message: str,
    max_tokens: int,
):
    """One Messages API call for the STRIPPED single-prompt baseline."""
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT_STRIPPED,
        messages=[{"role": "user", "content": user_message}],
    )


def _usage(response) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a Messages API response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )


def run_full_pipeline(
    scenario: Scenario,
    rep: int,
    model: str = "claude-sonnet-4-6",
    on_trace: Optional[Callable[[CallTrace], None]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ScenarioResult:
    """FULL branch: production agent loop with mocked tools.

    Mirrors backend/agent.py's run_agent but:
    - extract_clauses returns scenario clauses (no PDF parsing)
    - generate_redline_brief captures the conflicts list
    - every LLM call records a CallTrace via on_trace callback
    """
    client = _get_anthropic_client()
    start = time.time()
    error_msg: Optional[str] = None
    captured_conflicts: list[Any] = []
    captured_total: Optional[int] = None

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Analyze these two contracts for conflicts and generate "
                f"a complete redline brief.\n\n"
                f"Contract A (our company standard terms): "
                f"scenario://{scenario.id}/company\n"
                f"Contract B (vendor/supplier terms): "
                f"scenario://{scenario.id}/vendor\n\n"
                f"Follow your workflow: extract clauses from both, find "
                f"conflicts, then generate the final redline brief."
            ),
        }
    ]

    turn = 0
    try:
        while turn < MAX_TURNS:
            turn += 1
            t0 = time.time()
            response = _call_llm_full(client, model, messages, max_tokens)
            dt = time.time() - t0

            in_tok, out_tok = _usage(response)
            if on_trace is not None:
                on_trace(
                    make_trace(
                        model=model,
                        role="agent",
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        duration_seconds=dt,
                        scenario_id=scenario.id,
                        branch="full",
                        rep=rep,
                        turn_index=turn,
                    )
                )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    name = block.name
                    tool_input = dict(block.input or {})
                    if name == "extract_clauses":
                        result = _mock_extract_clauses(
                            scenario, tool_input.get("party_label", "")
                        )
                    elif name == "generate_redline_brief":
                        raw = tool_input.get("conflicts", [])
                        captured_conflicts = list(raw or [])
                        result = _mock_generate_redline_brief(captured_conflicts)
                        if result.get("success"):
                            captured_total = result["report"]["total_conflicts"]
                    else:
                        result = {"error": f"Unknown tool: {name}"}
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
                messages.append({"role": "user", "content": tool_results})
                continue

            # Any other stop_reason — break and record what we have.
            break
        else:
            error_msg = (
                f"Max turns ({MAX_TURNS}) reached without end_turn."
            )
    except Exception as exc:  # capture API/network errors
        error_msg = f"{type(exc).__name__}: {exc}"

    predicted = _coerce_conflicts(captured_conflicts)
    if captured_total is None and predicted:
        captured_total = len(predicted)

    return ScenarioResult(
        scenario_id=scenario.id,
        tier=scenario.tier,
        branch="full",
        rep=rep,
        predicted_conflicts=predicted if predicted or not error_msg else None,
        predicted_total=captured_total,
        error=error_msg,
        duration_seconds=time.time() - start,
    )


# ---------------------------------------------------------------------------
# STRIPPED branch
# ---------------------------------------------------------------------------


def run_stripped_pipeline(
    scenario: Scenario,
    rep: int,
    model: str = "claude-sonnet-4-6",
    on_trace: Optional[Callable[[CallTrace], None]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ScenarioResult:
    """STRIPPED branch: one LLM call with clauses inline. No tools."""
    client = _get_anthropic_client()
    start = time.time()
    error_msg: Optional[str] = None
    predicted: list[PredictedConflict] = []
    predicted_total: Optional[int] = None

    company_dicts = [
        {"section": c.section, "text": c.text, "party": c.party}
        for c in scenario.company_clauses
    ]
    vendor_dicts = [
        {"section": c.section, "text": c.text, "party": c.party}
        for c in scenario.vendor_clauses
    ]
    user_msg = render_stripped_user_message(company_dicts, vendor_dicts)

    try:
        t0 = time.time()
        response = _call_llm_stripped(client, model, user_msg, max_tokens)
        dt = time.time() - t0
        in_tok, out_tok = _usage(response)
        if on_trace is not None:
            on_trace(
                make_trace(
                    model=model,
                    role="stripped",
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    duration_seconds=dt,
                    scenario_id=scenario.id,
                    branch="stripped",
                    rep=rep,
                    turn_index=1,
                )
            )

        # Extract text from the response.
        text_out = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_out += block.text

        parsed = _parse_json_safe(text_out)
        raw_conflicts = parsed.get("conflicts", []) if parsed else []
        predicted_total = parsed.get("total_conflicts")
        if predicted_total is None and isinstance(raw_conflicts, list):
            predicted_total = len(raw_conflicts)
        if isinstance(raw_conflicts, list):
            predicted = _coerce_conflicts(raw_conflicts)

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    return ScenarioResult(
        scenario_id=scenario.id,
        tier=scenario.tier,
        branch="stripped",
        rep=rep,
        predicted_conflicts=predicted if predicted or not error_msg else None,
        predicted_total=predicted_total if predicted_total is not None else (
            len(predicted) if predicted else 0
        ),
        error=error_msg,
        duration_seconds=time.time() - start,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _status_message() -> str:
    return (
        "ClauseGuard eval harness — Day 8 status.\n"
        "Runners (FULL + STRIPPED) implemented. 30 scenarios committed.\n"
        "Scorers + orchestrator implemented. eval-small + eval are runnable.\n"
        "Run `make eval-small` for a 5-scenario verification ($0.50-$1).\n"
        "Run `make eval` for the full eval ($5-15)."
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="ClauseGuard eval harness CLI",
    )
    parser.add_argument(
        "--mode",
        choices=["dry", "small", "full"],
        default="dry",
        help=(
            "dry = status message (no API calls). "
            "small = 5-scenario eval (~$0.50-$1). "
            "full = all 30 scenarios x both branches x 3 reps (~$5-15)."
        ),
    )
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=Path(__file__).parent / "scenarios",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path(__file__).parent / "reports",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=None,
        help="Overrides default reps (small=1, full=3).",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Model id (default: claude-sonnet-4-6).",
    )
    args = parser.parse_args(argv)

    if args.mode == "dry":
        sys.stderr.write(_status_message() + "\n")
        return 1

    from eval.orchestrator import (  # noqa: PLC0415
        DEFAULT_EVAL_SMALL_SCENARIO_IDS,
        run_and_save,
    )

    if args.mode == "small":
        scenario_ids = DEFAULT_EVAL_SMALL_SCENARIO_IDS
        n_reps = args.reps if args.reps is not None else 1
    else:  # full
        scenario_ids = [
            p.stem for p in sorted(args.scenarios_dir.glob("*.json"))
        ]
        n_reps = args.reps if args.reps is not None else 3

    sys.stderr.write(
        f"Running {len(scenario_ids)} scenarios x 2 branches x {n_reps} reps "
        f"on {args.model}.\n"
        f"This will spend real API credits. Press Ctrl+C within 3 seconds to abort.\n"
    )
    import time as _time  # noqa: PLC0415
    _time.sleep(3)

    md_path, json_path, _ = run_and_save(
        scenario_ids=scenario_ids,
        branches=["full", "stripped"],
        n_reps=n_reps,
        scenarios_dir=args.scenarios_dir,
        reports_dir=args.reports_dir,
        model=args.model,
    )
    sys.stderr.write(f"\nReport written to: {md_path}\n")
    sys.stderr.write(f"Snapshot written to: {json_path}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
