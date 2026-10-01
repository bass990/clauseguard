"""Structured-output contract for ClauseGuard.

The 10-field conflict shape used to live only in the system prompt. It now
lives here as a Pydantic model, is exported as a strict JSON schema on the
generate_redline_brief tool, and is validated on every tool call. Invalid
conflicts are returned to the model as a tool error so it can repair them
(retry-with-error-feedback), and the parse-failure rate is recorded on the
analysis trace.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

Risk = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
Favor = Literal["Company", "Vendor"]


class Clause(BaseModel):
    section: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1, max_length=8000)
    party: Literal["company", "vendor"]
    suspected_injection: bool = False
    injection_patterns: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    """One conflict as the model must emit it."""

    id: int = Field(..., ge=1)
    risk: Risk
    topic: str = Field(..., min_length=1, max_length=200)
    company_section: str = Field(..., min_length=1, max_length=500)
    company_text: str = Field(..., min_length=1, max_length=8000)
    vendor_section: str = Field(..., min_length=1, max_length=500)
    vendor_text: str = Field(..., min_length=1, max_length=8000)
    conflict_explanation: str = Field(..., min_length=10, max_length=8000)
    favor: Favor
    resolution: str = Field(..., min_length=10, max_length=8000)
    playbook_ref: Optional[str] = None

    # Filled by the judge after generation, never by the model.
    resolution_review: Optional[dict] = None

    @field_validator("risk", mode="before")
    @classmethod
    def _upper_risk(cls, v):
        return v.upper().strip() if isinstance(v, str) else v

    @field_validator("favor", mode="before")
    @classmethod
    def _title_favor(cls, v):
        return v.strip().capitalize() if isinstance(v, str) else v


class RedlineReport(BaseModel):
    title: str = "Contract Conflict Analysis — Redline Brief"
    total_conflicts: int
    summary: dict[str, int]
    conflicts: list[Conflict]
    recommendation: str
    route: Optional[str] = None
    governing_law: Optional[str] = None


# JSON schema exposed on the tool. Strict: every field required, enums closed.
CONFLICT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "risk": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
        "topic": {"type": "string"},
        "company_section": {"type": "string"},
        "company_text": {"type": "string"},
        "vendor_section": {"type": "string"},
        "vendor_text": {"type": "string"},
        "conflict_explanation": {"type": "string"},
        "favor": {"type": "string", "enum": ["Company", "Vendor"]},
        "resolution": {"type": "string"},
        "playbook_ref": {"type": ["string", "null"]},
    },
    "required": [
        "id", "risk", "topic", "company_section", "company_text",
        "vendor_section", "vendor_text", "conflict_explanation", "favor", "resolution",
    ],
    "additionalProperties": False,
}


def validate_conflicts(raw: list) -> tuple[list[dict], list[str]]:
    """Validate a raw conflict list.

    Returns (valid_conflicts_as_dicts, error_messages). Ids are re-numbered
    sequentially so a dropped item never leaves a gap.
    """
    valid: list[dict] = []
    errors: list[str] = []
    if not isinstance(raw, list):
        return [], ["conflicts must be a JSON array"]
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"conflict[{i}]: not an object")
            continue
        data = dict(item)
        data.setdefault("id", i + 1)
        try:
            c = Conflict(**data)
        except ValidationError as exc:
            msgs = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            errors.append(f"conflict[{i}] (topic={data.get('topic', '?')!r}): {msgs}")
            continue
        valid.append(c.model_dump())
    for n, c in enumerate(valid, 1):
        c["id"] = n
    return valid, errors


def summarize(conflicts: list[dict]) -> dict[str, int]:
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for c in conflicts:
        r = str(c.get("risk", "LOW")).upper()
        if r in summary:
            summary[r] += 1
    return summary
