"""Playbook retrieval: the third tool.

The agent consults the company's negotiation playbook before assigning a
risk tier or drafting resolution language. Retrieval is a pure-Python BM25
over each entry's definition, standard position, fallbacks and precedents,
with a topic-alias boost so that "limitation of liability" reliably lands
on the liability_cap entry. Every hit carries an id the model must cite in
`playbook_ref`, which the judge later verifies.

No vector database is required for a 24-entry playbook; the interface is
deliberately the same shape a hybrid search over a real library would
return, so swapping the backend is a one-function change.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Optional

PLAYBOOK_PATH = Path(__file__).parent / "playbook.json"

_TOKEN = re.compile(r"[a-z0-9]+")

# Aliases mirror eval/rubric_audit.py TOPIC_SYNONYMS so that the topic the
# model names ("Limitation of Liability") maps to the entry key.
TOPIC_ALIASES: dict[str, list[str]] = {
    "liability_cap": ["liability", "limitation of liability", "cap on damages", "damages cap", "consequential damages"],
    "indemnification": ["indemnif", "indemnity", "hold harmless", "defend"],
    "ip_ownership": ["intellectual property", "ip ownership", "work product", "deliverables ownership", "ownership of"],
    "termination_rights": ["terminat", "term and termination", "for convenience", "cure period"],
    "governing_law": ["governing law", "jurisdiction", "venue", "choice of law", "applicable law"],
    "arbitration": ["arbitrat", "dispute resolution", "mediation", "class action"],
    "payment_terms": ["payment", "invoice", "net 30", "net 45", "late fee", "fees"],
    "penalties": ["penalt", "service credit", "liquidated damages", "credits"],
    "breach_consequences": ["breach", "default", "suspension", "remedies"],
    "confidentiality": ["confidential", "non-disclosure", "nda", "trade secret"],
    "exclusivity": ["exclusiv", "non-compete", "non-solicit", "preferred vendor"],
    "auto_renewal": ["auto-renew", "automatic renewal", "renewal", "evergreen", "non-renewal"],
    "warranty": ["warrant", "as is", "disclaimer", "conformance"],
    "notice_periods": ["notice", "days' notice", "advance notice", "written notice"],
    "amendments": ["amend", "modification", "modify", "unilateral"],
    "assignment": ["assign", "transfer", "successor", "change of control"],
    "subcontracting": ["subcontract", "subprocessor", "delegate"],
    "insurance": ["insurance", "coverage", "certificate of insurance", "policy limits"],
    "force_majeure": ["force majeure", "act of god", "beyond reasonable control"],
    "ambiguous_clause": ["ambiguous", "unclear", "interpretation"],
    "minor_inconsistency": ["inconsisten", "typo", "cross-reference", "numbering"],
    "data_protection": ["personal data", "data protection", "privacy", "gdpr", "security breach", "dpa"],
    "service_levels": ["service level", "sla", "uptime", "availability", "response time"],
    "audit_rights": ["audit", "inspect", "soc 2", "compliance report"],
}


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Playbook:
    """BM25 index over playbook entries with topic-alias boosting."""

    def __init__(self, entries: list[dict], k1: float = 1.5, b: float = 0.75):
        self.entries = entries
        self.k1, self.b = k1, b
        self.docs: list[list[str]] = []
        for e in entries:
            body = " ".join(
                [e["topic"].replace("_", " "), e["definition"], e["standard_position"]]
                + list(e.get("fallbacks", []))
                + [p["text"] for p in e.get("precedents", [])]
            )
            self.docs.append(_tokenize(body))
        self.n = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(self.n, 1)
        self.df: Counter = Counter()
        for d in self.docs:
            for t in set(d):
                self.df[t] += 1
        self.tf = [Counter(d) for d in self.docs]
        self.by_id = {e["id"]: e for e in entries}
        self.by_topic = {e["topic"]: e for e in entries}

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def _bm25(self, q: list[str], i: int) -> float:
        score = 0.0
        dl = len(self.docs[i])
        for t in q:
            f = self.tf[i].get(t, 0)
            if not f:
                continue
            score += self._idf(t) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return score

    def _alias_boost(self, query: str, entry: dict) -> float:
        q = query.lower()
        return 3.0 if any(a in q for a in TOPIC_ALIASES.get(entry["topic"], [])) else 0.0

    def search(self, query: str, top_k: int = 2) -> list[dict]:
        q = _tokenize(query)
        scored = []
        for i, e in enumerate(self.entries):
            s = self._bm25(q, i) + self._alias_boost(query, e)
            if s > 0:
                scored.append((s, e))
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "id": e["id"], "topic": e["topic"], "risk_tier": e["risk_tier"], "score": round(s, 3),
                "definition": e["definition"], "standard_position": e["standard_position"],
                "fallbacks": e["fallbacks"], "precedents": e["precedents"],
            }
            for s, e in scored[:top_k]
        ]

    def get(self, entry_id: str) -> Optional[dict]:
        return self.by_id.get(entry_id)


@lru_cache(maxsize=1)
def load_playbook(path: Optional[str] = None) -> Playbook:
    p = Path(path) if path else PLAYBOOK_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return Playbook(data["entries"])


def lookup_playbook(topic: str, top_k: int = 2) -> dict:
    """Tool function: retrieve the playbook entries most relevant to a topic."""
    hits = load_playbook().search(topic or "", top_k=max(1, min(int(top_k or 2), 5)))
    return {
        "success": True,
        "query": topic,
        "hits": hits,
        "note": (
            "Cite the entry id in playbook_ref. The standard position is the company's "
            "opening stance; fallbacks are acceptable compromises; precedents are past outcomes."
        ),
    }


def resolve_ref(ref: Optional[str]) -> Optional[dict]:
    """Return the entry (or precedent's parent entry) for a playbook_ref."""
    if not ref:
        return None
    pb = load_playbook()
    entry = pb.get(ref)
    if entry:
        return entry
    parent = ref.split("-p")[0]
    return pb.get(parent)
