"""Untrusted-input handling: prompt-injection scan and PII redaction.

Contract text is data the model must read, so injected instructions cannot
simply be deleted (the clause is still evidence). The defence is layered:

1. detection: scan every extracted clause for instruction-shaped text and
   tag it (`suspected_injection`, `injection_patterns`);
2. delimiting: clauses reach the model as <clause> elements with the tag
   surfaced as an attribute, and the system prompt states that clause
   content is data;
3. evidence: the pipeline reports how many suspected injections it saw so
   the reviewer knows the document tried something.

Redaction replaces PII with stable tokens (same input, same token) so that
counts and cross-references survive while nothing reversible leaves the
environment. It is opt-in (CLAUSEGUARD_REDACT=1) because contract clauses
legitimately contain company names and addresses that a redactor would
also hide.
"""
from __future__ import annotations

import hashlib
import re

INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions", re.I)),
    ("system_instruction", re.compile(r"\b(this is a|as a)\s+system\s+(instruction|message|prompt)\b", re.I)),
    ("role_override", re.compile(r"\byou are now\b|\bnew role\b|\bact as (an?|the) (assistant|system)\b", re.I)),
    ("flag_directive", re.compile(r"\b(flag|classify|mark|rate|treat)\s+(this|the|it|as)?\s*(clause|section|conflict)?\s*(as|to)?\s*(low|no|zero|critical|high|medium)\b[^.]{0,40}(risk|only|conflict)", re.I)),
    ("skip_directive", re.compile(r"\b(skip|omit|exclude|do not (generate|flag|report|include))\b[^.]{0,60}\b(conflict|section|clause|review)\b", re.I)),
    ("output_directive", re.compile(r"\b(return|output|set)\s+(total_conflicts|conflicts)\s*=", re.I)),
    ("reviewer_note", re.compile(r"\[\s*(attorney|reviewer|system|ai|llm|note)[^\]]{0,40}(note|instruction)[^\]]*\]", re.I)),
    ("pre_approved", re.compile(r"\bpre-?approved by\b[^.]{0,60}\b(legal|counsel)\b", re.I)),
    ("automated_review", re.compile(r"\bautomated\s+(review|system|tool)\b[^.]{0,60}\b(skip|ignore|flag|low)\b", re.I)),
]


def scan_injection(text: str) -> list[str]:
    """Return the names of injection patterns found in `text`."""
    if not text:
        return []
    return [name for name, pat in INJECTION_PATTERNS if pat.search(text)]


def tag_clauses(clauses: list[dict]) -> tuple[list[dict], int]:
    """Annotate clauses with injection flags. Returns (clauses, n_suspected)."""
    n = 0
    out = []
    for c in clauses:
        hits = scan_injection((c.get("section") or "") + " " + (c.get("text") or ""))
        cc = dict(c)
        cc["suspected_injection"] = bool(hits)
        cc["injection_patterns"] = hits
        n += bool(hits)
        out.append(cc)
    return out, n


def render_clauses_xml(clauses: list[dict]) -> str:
    """Serialize clauses as data-delimited XML for a prompt."""
    lines = []
    for c in clauses:
        flag = ' suspected_injection="true"' if c.get("suspected_injection") else ""
        section = _xml_escape(c.get("section", "?"))
        text = _xml_escape(c.get("text", ""))
        lines.append(f'  <clause section="{section}"{flag}>{text}</clause>')
    return "\n".join(lines)


def _xml_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------- redaction

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("PHONE", re.compile(r"(?<![\d-])(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
]


def _token(kind: str, value: str, salt: str) -> str:
    h = hashlib.sha256((salt + "|" + value).encode("utf-8")).hexdigest()[:8]
    return f"[{kind}_{h}]"


def redact(text: str, salt: str = "clauseguard") -> tuple[str, int]:
    """Replace PII with stable tokens. Returns (text, n_replacements)."""
    if not text:
        return text, 0
    n = 0
    out = text
    for kind, pat in _PII_PATTERNS:
        def _sub(m, kind=kind):
            nonlocal n
            n += 1
            return _token(kind, m.group(0), salt)
        out = pat.sub(_sub, out)
    return out, n


def redact_clauses(clauses: list[dict], salt: str = "clauseguard") -> tuple[list[dict], int]:
    total = 0
    out = []
    for c in clauses:
        cc = dict(c)
        cc["text"], k = redact(c.get("text", ""), salt)
        total += k
        out.append(cc)
    return out, total
