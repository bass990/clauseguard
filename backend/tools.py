import fitz  # PyMuPDF
import re
import json
from config import RISK_LEVELS, MAX_CLAUSES


# ─────────────────────────────────────────────
# TOOL FUNCTIONS
# ─────────────────────────────────────────────

def extract_clauses(pdf_path: str, party_label: str) -> dict:
    """Parse a contract PDF and return a list of clauses with section numbers."""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        total_chars = 0
        page_count = doc.page_count
        for page in doc:
            page_text = page.get_text()
            full_text += page_text
            total_chars += len(page_text.strip())
        doc.close()

        # Scanned PDFs produce near-empty text extraction
        avg_chars_per_page = total_chars / max(page_count, 1)
        if avg_chars_per_page < 80:
            return {
                "success": False,
                "error": (
                    f"'{party_label}' contract appears to be a scanned (image-based) PDF "
                    f"with only ~{int(avg_chars_per_page)} characters per page. "
                    "ClauseGuard requires text-based PDFs. "
                    "Please use an OCR tool (e.g. Adobe Acrobat, pdf2searchablepdf) "
                    "to convert the scanned document to a searchable PDF first."
                ),
                "party": party_label,
                "clauses": []
            }

        # Split into sections by common heading patterns
        lines = full_text.split("\n")
        clauses = []
        current_section = None
        current_text = []

        section_pattern = re.compile(
            r"^(\d+(\.\d+)*\.?\s+[A-Z][A-Za-z\s\-]+|"
            r"Section\s+\d+[\.\d]*\s*[:\-]?\s*\w+|"
            r"Article\s+\d+\s*[:\-]?\s*\w+)",
            re.IGNORECASE
        )

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if section_pattern.match(stripped) and len(stripped) < 120:
                if current_section and current_text:
                    clauses.append({
                        "section": current_section,
                        "text": " ".join(current_text).strip(),
                        "party": party_label
                    })
                current_section = stripped
                current_text = []
            else:
                if current_section:
                    current_text.append(stripped)

        if current_section and current_text:
            clauses.append({
                "section": current_section,
                "text": " ".join(current_text).strip(),
                "party": party_label
            })

        # Fallback: if no sections found, split by paragraphs
        if not clauses:
            paragraphs = [p.strip() for p in full_text.split("\n\n") if len(p.strip()) > 50]
            for i, para in enumerate(paragraphs[:MAX_CLAUSES], 1):
                clauses.append({
                    "section": f"Paragraph {i}",
                    "text": para[:800],
                    "party": party_label
                })

        total_found = len(clauses)
        truncated = total_found > MAX_CLAUSES
        clauses = clauses[:MAX_CLAUSES]

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
            "clauses": clauses
        }

    except Exception as e:
        return {"success": False, "error": str(e), "party": party_label, "clauses": []}



def generate_redline_brief(conflicts: list, output_format: str = "json") -> dict:
    """Compile all conflicts into a structured redline report."""
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for c in conflicts:
        risk = c.get("risk", "LOW").upper()
        if risk in summary:
            summary[risk] += 1

    report = {
        "title": "Contract Conflict Analysis — Redline Brief",
        "total_conflicts": len(conflicts),
        "summary": summary,
        "conflicts": conflicts,
        "recommendation": (
            "Review all CRITICAL and HIGH conflicts with legal counsel before signing. "
            "MEDIUM conflicts may be negotiated. LOW conflicts are informational."
        )
    }

    return {"success": True, "report": report}


# ─────────────────────────────────────────────
# TOOL SCHEMAS (for Claude)
# ─────────────────────────────────────────────

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
                "pdf_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the PDF file"
                },
                "party_label": {
                    "type": "string",
                    "description": "Label for this contract party: 'company' or 'vendor'"
                }
            },
            "required": ["pdf_path", "party_label"]
        }
    },
    {
        "name": "generate_redline_brief",
        "description": (
            "Compile all identified conflicts into a final structured redline brief. "
            "Call this as the last step after all conflicts have been identified and assessed. "
            "Include the risk level (CRITICAL/HIGH/MEDIUM/LOW) for each conflict."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conflicts": {
                    "type": "array",
                    "description": (
                        "Array of conflict objects. Each must have: "
                        "id (int), risk (str), topic (str), "
                        "company_section (str), company_text (str), "
                        "vendor_section (str), vendor_text (str), "
                        "conflict_explanation (str), favor (str), resolution (str)"
                    )
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format: 'json'",
                    "enum": ["json"]
                }
            },
            "required": ["conflicts", "output_format"]
        }
    }
]

TOOL_MAP = {
    "extract_clauses": extract_clauses,
    "generate_redline_brief": generate_redline_brief,
}
