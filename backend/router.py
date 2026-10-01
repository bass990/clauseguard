"""Conditional routing between the agentic loop and the single-prompt branch.

The June 2026 eval found the two-tool agentic loop wins on the
severity-tiering tier (+10.7pp F1) and loses on the ambiguous tier
(-13.0pp): the extra reasoning steps help when the question is *which
risk tier* and hurt when the question is *is this even a conflict*. The
router asks that question first, with a cheap model, and dispatches.

Two layers:
- a deterministic pre-router from clause topics (no model call): if the
  contract pair contains clauses on CRITICAL-tier topics, the tiering
  question dominates -> agentic; if no clause pair shares a topic at all,
  nothing to tier -> single;
- a model classifier (MODEL_FAST) for everything in between, returning a
  JSON decision with a one-line reason. Any failure falls back to the
  deterministic default, so routing can never take an analysis down.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Optional

from backend.playbook import TOPIC_ALIASES

CRITICAL_TOPICS = {"liability_cap", "indemnification", "ip_ownership", "termination_rights", "governing_law", "arbitration"}

ROUTER_SYSTEM = """You triage contract-comparison jobs for a legal review tool. Two engines exist:
- "agentic": a multi-step loop that extracts, consults a playbook per topic, then assigns risk tiers. It is better when the clauses clearly conflict and the hard part is deciding HOW SEVERE each conflict is.
- "single": one careful read of both clause lists. It is better when the hard part is deciding WHETHER borderline differences are conflicts at all (wording differences, small numeric gaps, restated obligations).
Given the topic overlap summary, answer with JSON only:
{"route": "agentic" | "single", "reason": "<one sentence>", "confidence": <0.0-1.0>}"""


@dataclass
class RouteDecision:
    route: str  # "agentic" | "single"
    reason: str
    confidence: float
    source: str  # "rule" | "model" | "fallback" | "forced"

    def to_dict(self) -> dict:
        return asdict(self)


def clause_topics(clauses: list[dict]) -> set[str]:
    """Deterministic topic detection by alias substring."""
    found: set[str] = set()
    for c in clauses:
        blob = ((c.get("section") or "") + " " + (c.get("text") or "")).lower()
        for topic, aliases in TOPIC_ALIASES.items():
            if any(a in blob for a in aliases):
                found.add(topic)
    return found


def rule_route(company: list[dict], vendor: list[dict]) -> Optional[RouteDecision]:
    """Pre-router. Returns a decision when the rule is confident, else None."""
    ct, vt = clause_topics(company), clause_topics(vendor)
    shared = ct & vt
    if not shared:
        return RouteDecision("single", "no shared topics between the two contracts; nothing to tier", 0.9, "rule")
    if shared & CRITICAL_TOPICS and len(shared) >= 2:
        return RouteDecision(
            "agentic",
            f"shared CRITICAL-tier topics ({', '.join(sorted(shared & CRITICAL_TOPICS))}); severity tiering dominates",
            0.8,
            "rule",
        )
    return None


def _summary(company: list[dict], vendor: list[dict]) -> str:
    ct, vt = clause_topics(company), clause_topics(vendor)
    return json.dumps(
        {
            "company_clauses": len(company),
            "vendor_clauses": len(vendor),
            "company_topics": sorted(ct),
            "vendor_topics": sorted(vt),
            "shared_topics": sorted(ct & vt),
            "sample_pairs": [
                {"company": c.get("text", "")[:240], "vendor": v.get("text", "")[:240]}
                for c, v in zip(company[:3], vendor[:3])
            ],
        }
    )


def parse_decision(text: str) -> Optional[RouteDecision]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    route = str(d.get("route", "")).lower()
    if route not in ("agentic", "single"):
        return None
    try:
        conf = float(d.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    return RouteDecision(route, str(d.get("reason", ""))[:300], max(0.0, min(1.0, conf)), "model")


def decide_route(
    company: list[dict],
    vendor: list[dict],
    client=None,
    model: str = "claude-haiku-4-5-20251001",
    mode: str = "auto",
    trace=None,
) -> RouteDecision:
    """Decide the branch. `client` is a sync Anthropic client (or None)."""
    if mode in ("agentic", "single"):
        return RouteDecision(mode, f"forced by CLAUSEGUARD_ROUTING={mode}", 1.0, "forced")
    rule = rule_route(company, vendor)
    if rule is not None:
        return rule
    fallback = RouteDecision("single", "router unavailable; single-prompt baseline is the safer default", 0.5, "fallback")
    if client is None:
        return fallback
    try:
        t0 = time.time()
        resp = client.messages.create(
            model=model,
            max_tokens=200,
            system=ROUTER_SYSTEM,
            messages=[{"role": "user", "content": _summary(company, vendor)}],
        )
        if trace is not None:
            trace.record_call("router", model, resp, time.time() - t0)
        text = "".join(getattr(b, "text", "") for b in resp.content)
        return parse_decision(text) or fallback
    except Exception as exc:  # network, auth, parse
        fallback.reason = f"router error ({type(exc).__name__}); single-prompt default"
        return fallback
