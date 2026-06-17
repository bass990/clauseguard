"""Cost and latency instrumentation for ClauseGuard eval runs.

Pricing is hard-coded against the model IDs ClauseGuard's config.py uses.
If pricing drifts, update PRICING and rerun the dry-run estimator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Per-million-token pricing in USD. Update from Anthropic's pricing page.
# Sonnet 4.6 numbers verified against Anthropic public pricing as of 2026-06.
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
}

# Fallback when a model id is not in PRICING. Conservative — assume sonnet rates.
FALLBACK_PRICING = {"input": 3.0, "output": 15.0}


@dataclass
class CallTrace:
    """One LLM call's cost + latency record."""

    model: str
    role: str  # "agent", "stripped", etc. — free-text label
    input_tokens: int
    output_tokens: int
    duration_seconds: float
    cost_usd: float

    # Optional bookkeeping.
    scenario_id: Optional[str] = None
    branch: Optional[str] = None
    rep: Optional[int] = None
    turn_index: Optional[int] = None


def cost_for_call(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost for one call given token counts."""
    pricing = PRICING.get(model, FALLBACK_PRICING)
    return (
        input_tokens * pricing["input"] / 1_000_000
        + output_tokens * pricing["output"] / 1_000_000
    )


def make_trace(
    model: str,
    role: str,
    input_tokens: int,
    output_tokens: int,
    duration_seconds: float,
    **bookkeeping,
) -> CallTrace:
    """Construct a CallTrace with cost computed automatically."""
    return CallTrace(
        model=model,
        role=role,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_seconds=duration_seconds,
        cost_usd=cost_for_call(model, input_tokens, output_tokens),
        **bookkeeping,
    )


@dataclass
class RunTotals:
    """Aggregated CallTrace records for a full eval run."""

    n_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0

    # Per-role rollup.
    per_role: dict[str, dict[str, float]] = field(default_factory=dict)


def aggregate_traces(traces: list[CallTrace]) -> RunTotals:
    """Roll up a list of CallTrace records into a RunTotals."""
    totals = RunTotals()
    for tr in traces:
        totals.n_calls += 1
        totals.total_input_tokens += tr.input_tokens
        totals.total_output_tokens += tr.output_tokens
        totals.total_duration_seconds += tr.duration_seconds
        totals.total_cost_usd += tr.cost_usd

        role_bucket = totals.per_role.setdefault(
            tr.role,
            {
                "n_calls": 0.0,
                "input_tokens": 0.0,
                "output_tokens": 0.0,
                "duration_seconds": 0.0,
                "cost_usd": 0.0,
            },
        )
        role_bucket["n_calls"] += 1
        role_bucket["input_tokens"] += tr.input_tokens
        role_bucket["output_tokens"] += tr.output_tokens
        role_bucket["duration_seconds"] += tr.duration_seconds
        role_bucket["cost_usd"] += tr.cost_usd

    return totals


def format_totals(totals: RunTotals) -> str:
    """Render a RunTotals as a human-readable markdown block."""
    lines = [
        f"- Total calls: **{totals.n_calls}**",
        f"- Total input tokens: **{totals.total_input_tokens:,}**",
        f"- Total output tokens: **{totals.total_output_tokens:,}**",
        f"- Total duration: **{totals.total_duration_seconds:.1f}s**",
        f"- Total cost: **${totals.total_cost_usd:.4f}**",
    ]
    if totals.per_role:
        lines.append("")
        lines.append("Per-role breakdown:")
        for role, bucket in sorted(totals.per_role.items()):
            lines.append(
                f"- `{role}`: {int(bucket['n_calls'])} calls, "
                f"${bucket['cost_usd']:.4f}, "
                f"{bucket['duration_seconds']:.1f}s"
            )
    return "\n".join(lines)
