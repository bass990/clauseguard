"""Tool implementations and schemas for the ClauseGuard agent.

Three tools:
- extract_clauses(pdf_path, party_label): PDF -> clause list (with optional
  OCR for scanned documents, injection tagging and optional PII redaction);
- lookup_playbook(topic, top_k): retrieval over the negotiation playbook;
- generate_redline_brief(conflicts): validates the conflict list against
  the Pydantic contract and either returns the report or the validation
  errors so the model can repair its output.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from config import MAX_CLAUSES, OCR_ENABLED, REDACT_ENABLED
from backend.playbook import lookup_playbook
from backend.sanitize import redact_clauses, tag_clauses
from backend.schemas import CONFLICT_ITEM_SCHEMA, summarize, validate_conflicts

SECTION_PATTERN = re.compile(
    r"^(\d+(\.\d+)*\.?\s+[A-Z][A-Za-z\s\-]+|"
    r"Section\s+\d+[\.\d]*\s*[:\-]?\s*\w+|"
    r"Article\s+\d+\s*[:\-]?\s*\w+)",
    re.IGNORECASE,
)

SCANNED_THRESHOLD_CHARS_PER_PAGE = 80


# ---------------------------------------------------------------- PDF text

def _ocr_page(page) -> str:
    """OCR one PyMuPDF page via pytesseract. Returns '' if OCR is unavailable."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return ""
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    elif os.name == "nt" and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img)


def read_pdf_text(pdf_path: str, ocr: bool = OCR_ENABLED) -> dict:
    """Return {'text', 'page_count', 'avg_chars_per_page', 'scanned', 'ocr_used'}."""
    import fitz  # PyMuPDF, imported lazily so tests can run without it

    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    page_count = doc.page_count
    total = sum(len(p.strip()) for p in pages)
    avg = total / max(page_count, 1)
    scanned = avg < SCANNED_THRESHOLD_CHARS_PER_PAGE
    ocr_used = False
    if scanned and ocr:
        ocr_pages = [_ocr_page(page) for page in doc]
        if sum(len(p.strip()) for p in ocr_pages) > total:
            pages = ocr_pages
            ocr_used = True
            scanned = False
    doc.close()
    return {
        "text": "\n".join(pages),
        "page_count": page_count,
        "avg_chars_per_page": avg,
        "scanned": scanned,
        "ocr_used": ocr_used,
    }


def split_into_clauses(full_text: str, party_label: str, max_clauses: int = MAX_CLAUSES) -> tuple[list[dict], int]:
    """Split raw contract text into (clauses, total_found)."""
    clauses: list[dict] = []
    current_section: Optional[str] = None
    current_text: list[str] = []
    for line in full_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if SECTION_PATTERN.match(stripped) and len(stripped) < 120:
            if current_section and current_text:
                clauses.append({"section": current_section, "text": " ".join(current_text).strip(), "party": party_label})
            current_section = stripped
            current_text = []
        elif current_section:
            current_text.append(stripped)
    if current_section and current_text:
        clauses.append({"section": current_section, "text": " ".join(current_text).strip(), "party": party_label})

    if not clauses:  # fallback: paragraphs
        paragraphs = [p.strip() for p in full_text.split("\n\n") if len(p.strip()) > 50]
        clauses = [
            {"section": f"Paragraph {i}", "text": para[:800], "party": party_label}
            for i, para in enumerate(paragraphs, 1)
        ]
    total_found = len(clauses)
    return clauses[:max_clauses], total_found


def extract_clauses(pdf_path: str, party_label: str, ocr: Optional[bool] = None, redact: Optional[bool] = None) -> dict:
    """Parse a contract PDF and return a list of clauses with section numbers."""
    try:
        info = read_pdf_text(pdf_path, ocr=OCR_ENABLED if ocr is None else ocr)
        if info["scanned"]:
            return {
                "success": False,
                "error": (
                    f"'{party_label}' contract appears to be a scanned (image-based) PDF "
                    f"with only ~{int(info['avg_chars_per_page'])} characters per page. "
                    + ("OCR is enabled but pytesseract/Tesseract is not installed. "
                       if (OCR_ENABLED if ocr is None else ocr) else
                       "Enable OCR with CLAUSEGUARD_OCR=1 (requires Tesseract), or ")
                    + "convert the document to a searchable PDF first."
                ),
                "party": party_label,
                "clauses": [],
            }
        clauses, total_found = split_into_clauses(info["text"], party_label)
        clauses, n_suspected = tag_clauses(clauses)
        n_redacted = 0
        if REDACT_ENABLED if redact is None else redact:
            clauses, n_redacted = redact_clauses(clauses)
        truncated = total_found > MAX_CLAUSES
        return {
            "success": True,
            "party": party_label,
            "clause_count": len(clauses),
            "total_found": total_found,
            "truncated": truncated,
            "truncation_warning": (
                f"Contract has {total_found} sections — only the first {MAX_CLAUSES} were analyzed. "
                "Conflicts in later sections may be missed."
            ) if truncated else None,
            "suspected_injections": n_suspected,
            "redactions": n_redacted,
            "ocr_used": info["ocr_used"],
            "page_count": info["page_count"],
            "clauses": clauses,
        }
    except Exception as e:  # unreadable file, corrupt PDF
        return {"success": False, "error": str(e), "party": party_label, "clauses": []}


def generate_redline_brief(conflicts: list, output_format: str = "json", route: Optional[str] = None,
                           governing_law: Optional[str] = None) -> dict:
    """Validate the conflict list and compile the redline report."""
    valid, errors = validate_conflicts(conflicts)
    if errors and not valid:
        return {
            "success": False,
            "error": "No conflict passed schema validation. Fix the listed fields and call generate_redline_brief again.",
            "validation_errors": errors[:20],
        }
    if errors:
        # Partial acceptance: report what validated, tell the model what was dropped.
        return {
            "success": False,
            "error": (
                f"{len(errors)} conflict(s) failed schema validation and were NOT included. "
                "Fix them and call generate_redline_brief again with the complete array."
            ),
            "validation_errors": errors[:20],
            "accepted_count": len(valid),
        }
    report = {
        "title": "Contract Conflict Analysis — Redline Brief",
        "total_conflicts": len(valid),
        "summary": summarize(valid),
        "conflicts": valid,
        "recommendation": (
            "Review all CRITICAL and HIGH conflicts with legal counsel before signing. "
            "MEDIUM conflicts may be negotiated. LOW conflicts are informational."
        ),
        "route": route,
        "governing_law": governing_law,
    }
    return {"success": True, "report": report}


# ---------------------------------------------------------------- schemas

TOOLS = [
    {
        "name": "extract_clauses",
        "description": (
            "Parse a contract PDF file and extract all clauses with their section numbers and text. "
            "Call this once for each contract before comparing them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pdf_path": {"type": "string", "description": "Absolute or relative path to the PDF file"},
                "party_label": {"type": "string", "enum": ["company", "vendor"],
                                "description": "Label for this contract party: 'company' or 'vendor'"},
            },
            "required": ["pdf_path", "party_label"],
        },
    },
    {
        "name": "lookup_playbook",
        "description": (
            "Retrieve the company's negotiation playbook entries for a clause topic: the standard "
            "position, acceptable fallbacks and past precedents. Call it for each conflict topic "
            "before assigning a risk tier or drafting resolution language, and cite the returned "
            "entry id in playbook_ref."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Clause topic or short description, e.g. 'limitation of liability'"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Number of entries to return (default 2)"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "generate_redline_brief",
        "description": (
            "Compile all identified conflicts into a final structured redline brief. "
            "Call this as the last step after all conflicts have been identified and assessed. "
            "Every conflict must match the schema exactly; validation errors are returned for repair."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conflicts": {"type": "array", "items": CONFLICT_ITEM_SCHEMA,
                              "description": "Array of conflict objects (10 required fields + optional playbook_ref)"},
                "output_format": {"type": "string", "enum": ["json"], "description": "Output format: 'json'"},
            },
            "required": ["conflicts", "output_format"],
        },
    },
]

TOOL_MAP = {
    "extract_clauses": extract_clauses,
    "lookup_playbook": lookup_playbook,
    "generate_redline_brief": generate_redline_brief,
}
