"""Programmatic encoding of the ClauseGuard eval rubric.

See eval/RUBRIC.md for prose authority. This module is the deterministic
subset — given a scenario's clause arrays, what conflicts SHOULD exist per
the rules in RUBRIC.md §1-4?

The scenario tests call rubric_canonical_conflicts() on every scenario and
verify the gold answer is consistent with this rubric. If a scenario's gold
disagrees with the rubric, the test FAILS until the scenario or the rubric
is updated explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from eval.schemas import Clause, Favor, Risk


# Per RUBRIC.md §2 — canonical risk for each canonical topic.
TOPIC_TO_CANONICAL_RISK: dict[str, Risk] = {
    "liability_cap": "CRITICAL",
    "indemnification": "CRITICAL",
    "ip_ownership": "CRITICAL",
    "termination_rights": "CRITICAL",
    "governing_law": "CRITICAL",
    "arbitration": "CRITICAL",
    "payment_terms": "HIGH",
    "penalties": "HIGH",
    "breach_consequences": "HIGH",
    "confidentiality": "HIGH",
    "exclusivity": "HIGH",
    "auto_renewal": "HIGH",
    "warranty": "HIGH",
    "notice_periods": "MEDIUM",
    "amendments": "MEDIUM",
    "assignment": "MEDIUM",
    "subcontracting": "MEDIUM",
    "insurance": "MEDIUM",
    "force_majeure": "MEDIUM",
    "ambiguous_clause": "LOW",
    "minor_inconsistency": "LOW",
}


# Per RUBRIC.md §3 — synonym lookup for matching predicted topic strings to
# canonical bucket keys. Order matters: longer/more-specific phrases first.
TOPIC_SYNONYMS: dict[str, list[str]] = {
    "liability_cap": [
        "limitation of liability", "cap on liability", "liability ceiling",
        "damages cap", "liability cap", "liability limit",
    ],
    "indemnification": [
        "indemnification scope", "indemnification clause", "hold harmless",
        "indemnification", "indemnity",
    ],
    "ip_ownership": [
        "intellectual property", "ownership of work", "ip assignment",
        "work product", "ip ownership", "ip rights",
    ],
    "termination_rights": [
        "termination for convenience", "termination for cause",
        "right to terminate", "termination rights", "termination",
    ],
    "governing_law": [
        "choice of law", "applicable law", "governing law",
        "jurisdiction", "venue",
    ],
    "arbitration": [
        "binding arbitration", "arbitration clause", "dispute resolution",
        "arbitration", "mediation",
    ],
    "payment_terms": [
        "payment schedule", "payment terms", "invoice",
        "net 30", "net 60", "net 90", "due date", "payment",
    ],
    "penalties": [
        "late fee", "late payment", "default penalty", "penalties",
    ],
    "confidentiality": [
        "non-disclosure", "trade secrets", "confidentiality", "nda",
    ],
    "exclusivity": [
        "exclusive dealing", "exclusivity", "exclusive", "non-compete",
    ],
    "auto_renewal": [
        "automatic renewal", "evergreen clause", "auto-renewal", "renewal",
    ],
    "warranty": [
        "representations and warranties", "warranties", "warranty",
    ],
    "breach_consequences": [
        "material breach", "cure period", "remedies for breach", "breach",
    ],
    "notice_periods": [
        "notice period", "notice requirement", "advance notice", "notice",
    ],
    "amendments": [
        "changes to agreement", "amendments", "amendment", "modification",
    ],
    "assignment": [
        "assignability", "transfer of agreement", "assignment",
    ],
    "subcontracting": [
        "subcontracting", "subcontractors", "delegation",
    ],
    "insurance": [
        "insurance requirements", "coverage", "insurance",
    ],
    "force_majeure": [
        "act of god", "uncontrollable circumstances", "force majeure",
    ],
    "minor_inconsistency": [
        "minor inconsistency", "stylistic difference",
    ],
    "ambiguous_clause": [
        "ambiguous clause", "ambiguous", "unclear language",
    ],
}


@dataclass
class CanonicalConflict:
    """A conflict per the rubric, derivable from clause arrays alone."""

    canonical_topic: str
    canonical_risk: Risk
    canonical_favor: Favor
    company_section: Optional[str] = None
    vendor_section: Optional[str] = None


def normalize_topic(topic: str) -> str:
    """Lowercase + strip + collapse whitespace for topic comparison."""
    return " ".join(topic.lower().strip().split())


def topic_to_canonical(topic_str: str) -> Optional[str]:
    """Map a free-text topic string to its canonical bucket key, or None.

    The matching is case-insensitive substring lookup against TOPIC_SYNONYMS
    values. Longer phrases are checked first to avoid greedy matches.
    """
    norm = normalize_topic(topic_str)
    if not norm:
        return None

    # Sort canonical buckets so longest synonyms across all buckets are
    # checked first — prevents "payment" matching before "payment terms".
    candidates: list[tuple[int, str, str]] = []
    for bucket, synonyms in TOPIC_SYNONYMS.items():
        for syn in synonyms:
            candidates.append((len(syn), bucket, syn))
    candidates.sort(key=lambda t: -t[0])

    for _, bucket, syn in candidates:
        if syn in norm:
            return bucket
    return None


def canonical_risk_for(canonical_topic: str) -> Risk:
    """Lookup canonical risk for a canonical-topic bucket key.

    Falls back to LOW for unknown topics (per RUBRIC.md §2 the LOW tier
    catches ambiguous/minor inconsistencies).
    """
    return TOPIC_TO_CANONICAL_RISK.get(canonical_topic, "LOW")


def clauses_by_topic(clauses: list[Clause]) -> dict[str, list[Clause]]:
    """Group a clause list by canonical topic.

    Uses the clause's explicit `canonical_topic` annotation if present
    (scenario author marks the clause's intended topic). Falls back to
    substring matching against TOPIC_SYNONYMS over clause text.
    """
    grouped: dict[str, list[Clause]] = {}
    for clause in clauses:
        topic = clause.canonical_topic
        if topic is None:
            topic = topic_to_canonical(clause.text)
        if topic is None:
            continue
        grouped.setdefault(topic, []).append(clause)
    return grouped


def rubric_canonical_conflicts(
    company_clauses: list[Clause],
    vendor_clauses: list[Clause],
    favor_overrides: Optional[dict[str, Favor]] = None,
) -> list[CanonicalConflict]:
    """Derive the canonical conflict list per RUBRIC.md §1-4.

    Implements Rules 1 and 3 — same-topic clauses in both contracts produce
    a conflict candidate. The favor field defaults to "Company" (company's
    standard terms are presumed favorable to the company unless flagged
    otherwise) and can be overridden per-topic via favor_overrides for
    scenarios where vendor language is genuinely better for the company.

    This function deliberately does NOT cover Rule 2 (no fabrication) or
    Rule 4 (ambiguity carve-out) — those are scenario-author judgment calls
    encoded by the `is_optional` flag on individual ExpectedConflict entries.

    The scenario tests use the output of this function as a baseline and
    cross-check that the scenario's gold conflict list is consistent.
    """
    favor_overrides = favor_overrides or {}

    company_by_topic = clauses_by_topic(company_clauses)
    vendor_by_topic = clauses_by_topic(vendor_clauses)

    conflicts: list[CanonicalConflict] = []
    shared_topics = set(company_by_topic.keys()) & set(vendor_by_topic.keys())

    for topic in sorted(shared_topics):
        company_clause = company_by_topic[topic][0]
        vendor_clause = vendor_by_topic[topic][0]
        favor = favor_overrides.get(topic, "Company")
        conflicts.append(
            CanonicalConflict(
                canonical_topic=topic,
                canonical_risk=canonical_risk_for(topic),
                canonical_favor=favor,
                company_section=company_clause.section,
                vendor_section=vendor_clause.section,
            )
        )

    return conflicts
