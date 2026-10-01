"""Pipeline runners for the eval harness.

Five branches, one per architecture the README discusses:

  full          the two-tool agentic loop as evaluated in June 2026 (no playbook)
  stripped      one LLM call, clauses inline, no tools (June 2026 baseline)
  full_rag      the agentic loop with the lookup_playbook tool (production "agentic")
  stripped_rag  one call with playbook entries pre-retrieved inline (production "single")
  routed        backend.router decides per scenario, then full_rag or stripped_rag

extract_clauses is MOCKED to return scenario clauses (the eval tests
reasoning, not PDF parsing). lookup_playbook and generate_redline_brief run
the real production code, so schema validation and retrieval are measured.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from backend.playbook import lookup_playbook
from backend.router import clause_topics, decide_route
from backend.schemas import validate_conflicts
from backend.tools import TOOLS as PRODUCTION_TOOLS
from eval.instrumentation import make_trace
from eval.prompts import (
    SYSTEM_PROMPT_FULL_EVAL,
    SYSTEM_PROMPT_STRIPPED,
    render_stripped_user_message,
)
from eval.schemas import BRANCHES, PredictedConflict, Scenario, ScenarioResult

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_FAST_MODEL = "claude-haiku-4-5-20251001"

_ANTHROPIC_CLIENT = None


def _get_anthropic_client():
    """Lazy-load the Anthropic client. Patched in tests."""
    global _ANTHROPIC_CLIENT
    if _ANTHROPIC_CLIENT is None:
        import anthropic  # noqa: PLC0415
        _ANTHROPIC_CLIENT = anthropic.Anthropic(max_retries=3, timeout=120)
    return _ANTHROPIC_CLIENT


# The eval uses the production tool schemas directly: no mirror to drift.
TOOLS_FOR_EVAL: list[dict] = PRODUCTION_TOOLS
TOOLS_WITHOUT_PLAYBOOK: list[dict] = [t for t in PRODUCTION_TOOLS if t["name"] != "lookup_playbook"]


# ---------------------------------------------------------------------------
# Scenario IO
# ---------------------------------------------------------------------------


def load_scenario(scenario_path: Path) -> Scenario:
    with scenario_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return Scenario(**data)


def list_scenarios(scenarios_dir: Path) -> list[Scenario]:
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


def _coerce_conflicts(raw_conflicts: list[Any]) -> list[PredictedConflict]:
    """Coerce raw conflict dicts into PredictedConflict objects, skipping malformed ones."""
    out: list[PredictedConflict] = []
    for i, raw in enumerate(raw_conflicts):
        if not isinstance(raw, dict):
            continue
        if "id" not in raw:
            raw = dict(raw)
            raw["id"] = i + 1
        try:
            out.append(PredictedConflict(**raw))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Mocked / real tool implementations
# ---------------------------------------------------------------------------


def _clause_dicts(clauses) -> list[dict]:
    return [{"section": c.section, "text": c.text, "party": c.party} for c in clauses]


def _mock_extract_clauses(scenario: Scenario, party_label: str) -> dict[str, Any]:
    label = (party_label or "").lower().strip()
    if label == "company":
        clauses = scenario.company_clauses
    elif label == "vendor":
        clauses = scenario.vendor_clauses
    else:
        return {"success": False, "error": f"Unknown party_label: '{party_label}'", "party": party_label, "clauses": []}
    serialized = _clause_dicts(clauses)
    return {
        "success": True, "party": label, "clause_count": len(serialized),
        "total_found": len(serialized), "truncated": False, "clauses": serialized,
    }


def _mock_generate_redline_brief(conflicts: list[Any]) -> dict[str, Any]:
    """Capture the agent's conflicts. Runs the production validator so schema
    errors are fed back to the model exactly as in production."""
    valid, errors = validate_conflicts(list(conflicts or []))
    if errors:
        return {
            "success": False,
            "error": f"{len(errors)} conflict(s) failed schema validation and were NOT included. Fix them and call again.",
            "validation_errors": errors[:20], "accepted_count": len(valid),
        }
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for c in valid:
        summary[c["risk"]] += 1
    return {"success": True, "report": {"title": "Contract Conflict Analysis — Redline Brief",
                                        "total_conflicts": len(valid), "summary": summary, "conflicts": valid}}


def _playbook_context(scenario: Scenario) -> list[dict]:
    """Pre-retrieval for the stripped_rag branch (mirrors backend.pipeline._retrieve_for_single)."""
    company, vendor = _clause_dicts(scenario.company_clauses), _clause_dicts(scenario.vendor_clauses)
    topics = clause_topics(company) | clause_topics(vendor)
    seen, hits = set(), []
    for t in sorted(topics):
        for h in lookup_playbook(t.replace("_", " "), 1)["hits"]:
            if h["id"] not in seen:
                seen.add(h["id"])
                hits.append({k: h[k] for k in ("id", "topic", "risk_tier", "standard_position", "fallbacks")})
    return hits


# ---------------------------------------------------------------------------
# Agentic loop (full / full_rag)
# ---------------------------------------------------------------------------


MAX_TURNS = 20
DEFAULT_MAX_TOKENS = 8192


def _call_llm_full(client, model: str, messages: list[dict], max_tokens: int, tools: list[dict]):
    return client.messages.create(
        model=model, max_tokens=max_tokens,
        system=[{"type": "text", "text": SYSTEM_PROMPT_FULL_EVAL, "cache_control": {"type": "ephemeral"}}],
        tools=tools, messages=messages,
    )


def _call_llm_stripped(client, model: str, user_message: str, max_tokens: int):
    return client.messages.create(
        model=model, max_tokens=max_tokens, system=SYSTEM_PROMPT_STRIPPED,
        messages=[{"role": "user", "content": user_message}],
    )


def _usage(response) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)


def _run_agent_loop(
    scenario: Scenario, rep: int, model: str, on_trace, max_tokens: int, branch: str, playbook: bool,
) -> ScenarioResult:
    client = _get_anthropic_client()
    start = time.time()
    error_msg: Optional[str] = None
    captured_conflicts: list[Any] = []
    captured_total: Optional[int] = None
    playbook_calls = 0
    schema_retries = 0
    tools = TOOLS_FOR_EVAL if playbook else TOOLS_WITHOUT_PLAYBOOK

    messages: list[dict] = [{
        "role": "user",
        "content": (
            "Analyze these two contracts for conflicts and generate a complete redline brief.\n\n"
            f"Contract A (our company standard terms): scenario://{scenario.id}/company\n"
            f"Contract B (vendor/supplier terms): scenario://{scenario.id}/vendor\n\n"
            "Follow your workflow: extract clauses from both, "
            + ("consult the playbook per conflict topic, " if playbook else "")
            + "find conflicts, then generate the final redline brief."
        ),
    }]

    turn = 0
    try:
        while turn < MAX_TURNS:
            turn += 1
            t0 = time.time()
            response = _call_llm_full(client, model, messages, max_tokens, tools)
            dt = time.time() - t0
            in_tok, out_tok = _usage(response)
            if on_trace is not None:
                on_trace(make_trace(model=model, role="agent", input_tokens=in_tok, output_tokens=out_tok,
                                    duration_seconds=dt, scenario_id=scenario.id, branch=branch, rep=rep, turn_index=turn))
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
                        result = _mock_extract_clauses(scenario, tool_input.get("party_label", ""))
                    elif name == "lookup_playbook":
                        playbook_calls += 1
                        result = lookup_playbook(tool_input.get("topic", ""), tool_input.get("top_k", 2))
                    elif name == "generate_redline_brief":
                        raw = tool_input.get("conflicts", [])
                        result = _mock_generate_redline_brief(raw)
                        if result.get("success"):
                            captured_conflicts = list(result["report"]["conflicts"])
                            captured_total = result["report"]["total_conflicts"]
                        else:
                            schema_retries += 1
                    else:
                        result = {"error": f"Unknown tool: {name}"}
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
                messages.append({"role": "user", "content": tool_results})
                continue
            break
        else:
            error_msg = f"Max turns ({MAX_TURNS}) reached without end_turn."
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    predicted = _coerce_conflicts(captured_conflicts)
    if captured_total is None and predicted:
        captured_total = len(predicted)
    return ScenarioResult(
        scenario_id=scenario.id, tier=scenario.tier, branch=branch, rep=rep,
        predicted_conflicts=predicted if predicted or not error_msg else None,
        predicted_total=captured_total, error=error_msg, duration_seconds=time.time() - start,
        playbook_calls=playbook_calls, schema_retries=schema_retries,
    )


def run_full_pipeline(scenario: Scenario, rep: int, model: str = DEFAULT_MODEL, on_trace=None,
                      max_tokens: int = DEFAULT_MAX_TOKENS) -> ScenarioResult:
    """FULL branch: agentic loop, no playbook (June 2026 architecture)."""
    return _run_agent_loop(scenario, rep, model, on_trace, max_tokens, "full", playbook=False)


def run_full_rag_pipeline(scenario: Scenario, rep: int, model: str = DEFAULT_MODEL, on_trace=None,
                          max_tokens: int = DEFAULT_MAX_TOKENS) -> ScenarioResult:
    """FULL_RAG branch: agentic loop with the lookup_playbook tool (production agentic)."""
    return _run_agent_loop(scenario, rep, model, on_trace, max_tokens, "full_rag", playbook=True)


# ---------------------------------------------------------------------------
# Single call (stripped / stripped_rag)
# ---------------------------------------------------------------------------


def _run_single_call(scenario: Scenario, rep: int, model: str, on_trace, max_tokens: int, branch: str, playbook: bool) -> ScenarioResult:
    client = _get_anthropic_client()
    start = time.time()
    error_msg: Optional[str] = None
    predicted: list[PredictedConflict] = []
    predicted_total: Optional[int] = None

    hits = _playbook_context(scenario) if playbook else None
    user_msg = render_stripped_user_message(_clause_dicts(scenario.company_clauses), _clause_dicts(scenario.vendor_clauses), hits)
    try:
        t0 = time.time()
        response = _call_llm_stripped(client, model, user_msg, max_tokens)
        dt = time.time() - t0
        in_tok, out_tok = _usage(response)
        if on_trace is not None:
            on_trace(make_trace(model=model, role="stripped", input_tokens=in_tok, output_tokens=out_tok,
                                duration_seconds=dt, scenario_id=scenario.id, branch=branch, rep=rep, turn_index=1))
        text_out = "".join(getattr(b, "text", "") for b in response.content if hasattr(b, "text"))
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
        scenario_id=scenario.id, tier=scenario.tier, branch=branch, rep=rep,
        predicted_conflicts=predicted if predicted or not error_msg else None,
        predicted_total=predicted_total if predicted_total is not None else (len(predicted) if predicted else 0),
        error=error_msg, duration_seconds=time.time() - start,
        playbook_calls=len(hits) if hits else 0,
    )


def run_stripped_pipeline(scenario: Scenario, rep: int, model: str = DEFAULT_MODEL, on_trace=None,
                          max_tokens: int = DEFAULT_MAX_TOKENS) -> ScenarioResult:
    """STRIPPED branch: one call, clauses inline, no playbook (June 2026 baseline)."""
    return _run_single_call(scenario, rep, model, on_trace, max_tokens, "stripped", playbook=False)


def run_stripped_rag_pipeline(scenario: Scenario, rep: int, model: str = DEFAULT_MODEL, on_trace=None,
                              max_tokens: int = DEFAULT_MAX_TOKENS) -> ScenarioResult:
    """STRIPPED_RAG branch: one call with playbook entries pre-retrieved (production single)."""
    return _run_single_call(scenario, rep, model, on_trace, max_tokens, "stripped_rag", playbook=True)


# ---------------------------------------------------------------------------
# Routed
# ---------------------------------------------------------------------------


def run_routed_pipeline(scenario: Scenario, rep: int, model: str = DEFAULT_MODEL, on_trace=None,
                        max_tokens: int = DEFAULT_MAX_TOKENS, fast_model: str = DEFAULT_FAST_MODEL) -> ScenarioResult:
    """ROUTED branch: backend.router picks agentic (full_rag) or single (stripped_rag)."""
    client = _get_anthropic_client()
    company, vendor = _clause_dicts(scenario.company_clauses), _clause_dicts(scenario.vendor_clauses)

    class _T:  # minimal trace adapter so the router's model call is costed
        def record_call(self, name, model_id, response, duration_s, note=""):
            in_tok, out_tok = _usage(response)
            if on_trace is not None:
                on_trace(make_trace(model=model_id, role="router", input_tokens=in_tok, output_tokens=out_tok,
                                    duration_seconds=duration_s, scenario_id=scenario.id, branch="routed", rep=rep, turn_index=0))

    decision = decide_route(company, vendor, client=client, model=fast_model, mode="auto", trace=_T())
    if decision.route == "agentic":
        result = _run_agent_loop(scenario, rep, model, on_trace, max_tokens, "routed", playbook=True)
    else:
        result = _run_single_call(scenario, rep, model, on_trace, max_tokens, "routed", playbook=True)
    result.route = decision.route
    result.route_source = decision.source
    return result


RUNNERS: dict[str, Callable[..., ScenarioResult]] = {
    "full": run_full_pipeline,
    "stripped": run_stripped_pipeline,
    "full_rag": run_full_rag_pipeline,
    "stripped_rag": run_stripped_rag_pipeline,
    "routed": run_routed_pipeline,
}
assert set(RUNNERS) == set(BRANCHES)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _status_message() -> str:
    return (
        "ClauseGuard eval harness.\n"
        f"Branches: {', '.join(BRANCHES)}. 30 scenarios across 5 tiers.\n"
        "Run `make eval-small` for a 5-scenario verification (~$1-2).\n"
        "Run `make eval` for the full eval (~$15-25 across all five branches)."
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ClauseGuard eval harness CLI")
    parser.add_argument("--mode", choices=["dry", "small", "full"], default="dry")
    parser.add_argument("--scenarios-dir", type=Path, default=Path(__file__).parent / "scenarios")
    parser.add_argument("--reports-dir", type=Path, default=Path(__file__).parent / "reports")
    parser.add_argument("--reps", type=int, default=None, help="Overrides default reps (small=1, full=3).")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--branches", default=",".join(BRANCHES), help="Comma-separated subset of branches.")
    parser.add_argument("--yes", action="store_true", help="Skip the 3-second abort window.")
    parser.add_argument("--resume", action="store_true",
                        help="Reuse successful runs from reports/latest_run.json; run only missing or errored cells.")
    parser.add_argument("--rerender", action="store_true",
                        help="Re-render the markdown report from reports/latest_run.json without any model calls.")
    args = parser.parse_args(argv)

    if args.rerender:
        from eval.orchestrator import rerender_snapshot  # noqa: PLC0415
        md_path = rerender_snapshot(args.reports_dir, scenarios_dir=args.scenarios_dir)
        sys.stderr.write(f"Report re-rendered: {md_path}\n")
        return 0

    if args.mode == "dry":
        sys.stderr.write(_status_message() + "\n")
        return 1

    from eval.orchestrator import DEFAULT_EVAL_SMALL_SCENARIO_IDS, run_and_save  # noqa: PLC0415

    branches = [b.strip() for b in args.branches.split(",") if b.strip()]
    unknown = set(branches) - set(BRANCHES)
    if unknown:
        parser.error(f"unknown branches: {sorted(unknown)}")

    if args.mode == "small":
        scenario_ids = DEFAULT_EVAL_SMALL_SCENARIO_IDS
        n_reps = args.reps if args.reps is not None else 1
    else:
        scenario_ids = [p.stem for p in sorted(args.scenarios_dir.glob("*.json"))]
        n_reps = args.reps if args.reps is not None else 3

    sys.stderr.write(
        f"Running {len(scenario_ids)} scenarios x {len(branches)} branches x {n_reps} reps on {args.model}.\n"
        "This will spend real API credits." + ("" if args.yes else " Press Ctrl+C within 3 seconds to abort.") + "\n"
    )
    if not args.yes:
        time.sleep(3)

    resume_snapshot = None
    if args.resume:
        snap_path = args.reports_dir / "latest_run.json"
        if not snap_path.exists():
            parser.error(f"--resume given but {snap_path} does not exist")
        resume_snapshot = json.loads(snap_path.read_text(encoding="utf-8"))

    md_path, json_path, _ = run_and_save(
        scenario_ids=scenario_ids, branches=branches, n_reps=n_reps,
        scenarios_dir=args.scenarios_dir, reports_dir=args.reports_dir, model=args.model,
        resume_snapshot=resume_snapshot,
    )
    sys.stderr.write(f"\nReport written to: {md_path}\nSnapshot written to: {json_path}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
