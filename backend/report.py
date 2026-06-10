import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ─────────────────────────────────────────────
# COLOR PALETTE
# ─────────────────────────────────────────────

NAVY       = colors.HexColor("#1E3A5F")
NAVY_LIGHT = colors.HexColor("#EEF2F7")
PURPLE     = colors.HexColor("#7C3AED")

RISK_FG = {
    "CRITICAL": colors.HexColor("#DC2626"),
    "HIGH":     colors.HexColor("#EA580C"),
    "MEDIUM":   colors.HexColor("#D97706"),
    "LOW":      colors.HexColor("#16A34A"),
}
RISK_BG = {
    "CRITICAL": colors.HexColor("#FEF2F2"),
    "HIGH":     colors.HexColor("#FFF7ED"),
    "MEDIUM":   colors.HexColor("#FFFBEB"),
    "LOW":      colors.HexColor("#F0FDF4"),
}
RISK_BORDER = {
    "CRITICAL": colors.HexColor("#FECACA"),
    "HIGH":     colors.HexColor("#FED7AA"),
    "MEDIUM":   colors.HexColor("#FDE68A"),
    "LOW":      colors.HexColor("#BBF7D0"),
}


# ─────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()

    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            fontSize=28, fontName="Helvetica-Bold",
            textColor=NAVY, alignment=TA_CENTER, spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            fontSize=13, fontName="Helvetica",
            textColor=colors.HexColor("#64748B"), alignment=TA_CENTER, spaceAfter=4,
        ),
        "cover_date": ParagraphStyle(
            "cover_date",
            fontSize=10, fontName="Helvetica",
            textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontSize=14, fontName="Helvetica-Bold",
            textColor=NAVY, spaceBefore=18, spaceAfter=6,
        ),
        "conflict_title": ParagraphStyle(
            "conflict_title",
            fontSize=11, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1E293B"), spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#64748B"), spaceAfter=2,
        ),
        "clause_text": ParagraphStyle(
            "clause_text",
            fontSize=9, fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#1E293B"),
            leftIndent=6, spaceAfter=2,
        ),
        "section_ref": ParagraphStyle(
            "section_ref",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#475569"), spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            fontSize=9, fontName="Helvetica",
            textColor=colors.HexColor("#374151"), spaceAfter=4, leading=13,
        ),
        "resolution": ParagraphStyle(
            "resolution",
            fontSize=9, fontName="Helvetica",
            textColor=colors.HexColor("#1E3A5F"),
            leftIndent=8, spaceAfter=4, leading=13,
        ),
        "recommendation": ParagraphStyle(
            "recommendation",
            fontSize=10, fontName="Helvetica",
            textColor=colors.HexColor("#374151"), leading=15,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontSize=8, fontName="Helvetica",
            textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER,
        ),
    }


# ─────────────────────────────────────────────
# PAGE TEMPLATE
# ─────────────────────────────────────────────

def _make_page_decorator(title: str):
    def decorator(canvas, doc):
        canvas.saveState()
        w, h = LETTER

        # Top bar
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 0.45 * inch, w, 0.45 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(0.5 * inch, h - 0.28 * inch, "ClauseGuard")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(w - 0.5 * inch, h - 0.28 * inch, title)

        # Bottom bar
        canvas.setFillColor(NAVY_LIGHT)
        canvas.rect(0, 0, w, 0.4 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.5 * inch, 0.14 * inch, "Confidential — For review purposes only")
        canvas.drawRightString(w - 0.5 * inch, 0.14 * inch, f"Page {doc.page}")

        canvas.restoreState()
    return decorator


# ─────────────────────────────────────────────
# COVER PAGE
# ─────────────────────────────────────────────

def _cover(report: dict, s: dict) -> list:
    summary = report.get("summary", {})
    generated = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    total = report.get("total_conflicts", 0)

    elements = [Spacer(1, 1.2 * inch)]

    # Logo block
    elements.append(Paragraph("ClauseGuard", s["cover_title"]))
    elements.append(Paragraph("Contract Conflict Analysis — Redline Brief", s["cover_sub"]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(HRFlowable(width="60%", thickness=2, color=PURPLE, hAlign="CENTER"))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(f"Generated {generated}", s["cover_date"]))

    elements.append(Spacer(1, 0.6 * inch))

    # Summary table
    summary_data = [
        [
            _risk_badge_cell("CRITICAL", summary.get("CRITICAL", 0)),
            _risk_badge_cell("HIGH",     summary.get("HIGH", 0)),
            _risk_badge_cell("MEDIUM",   summary.get("MEDIUM", 0)),
            _risk_badge_cell("LOW",      summary.get("LOW", 0)),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[1.4 * inch] * 4)
    summary_table.setStyle(TableStyle([
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)

    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(f"{total} total conflict{'s' if total != 1 else ''} identified", s["cover_sub"]))

    elements.append(Spacer(1, 0.6 * inch))
    elements.append(HRFlowable(width="80%", thickness=1, color=colors.HexColor("#E2E8F0"), hAlign="CENTER"))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(
        "Review all CRITICAL and HIGH conflicts with legal counsel before signing.",
        s["cover_sub"]
    ))

    elements.append(PageBreak())
    return elements


def _risk_badge_cell(risk: str, count: int):
    fg = RISK_FG.get(risk, colors.black)
    bg = RISK_BG.get(risk, colors.white)
    border = RISK_BORDER.get(risk, colors.grey)
    label = risk.capitalize()

    inner = Table(
        [[Paragraph(f'<font size="18"><b>{count}</b></font>', ParagraphStyle("n", alignment=TA_CENTER, textColor=fg))],
         [Paragraph(f'<font size="8">{label}</font>', ParagraphStyle("l", alignment=TA_CENTER, textColor=fg))]],
        colWidths=[1.2 * inch],
        rowHeights=[0.35 * inch, 0.22 * inch],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("BOX",           (0, 0), (-1, -1), 1, border),
        ("ROUNDEDCORNERS",(0, 0), (-1, -1), [4, 4, 4, 4]),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return inner


# ─────────────────────────────────────────────
# CONFLICT CARDS
# ─────────────────────────────────────────────

def _conflict_card(conflict: dict, s: dict) -> list:
    risk  = conflict.get("risk", "LOW").upper()
    topic = conflict.get("topic", "Unknown")
    favor = conflict.get("favor", "")
    idx   = conflict.get("id", "?")

    fg     = RISK_FG.get(risk, colors.black)
    bg     = RISK_BG.get(risk, colors.white)
    border = RISK_BORDER.get(risk, colors.grey)

    elements = []

    # Header row: risk badge + topic + favor
    header_data = [[
        Paragraph(f'<font color="#{_hex(fg)}"><b>{risk}</b></font>',
                  ParagraphStyle("rh", fontSize=9, fontName="Helvetica-Bold", textColor=fg)),
        Paragraph(f'<b>{idx}. {topic}</b>',
                  ParagraphStyle("th", fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#1E293B"))),
        Paragraph(f'Favors: <b>{favor}</b>',
                  ParagraphStyle("fh", fontSize=9, fontName="Helvetica", textColor=colors.HexColor("#64748B"), alignment=TA_RIGHT)),
    ]]
    header_table = Table(header_data, colWidths=[0.85 * inch, 3.9 * inch, 1.75 * inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("BOX",           (0, 0), (-1, -1), 1, border),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)

    # Clause comparison table
    company_section = conflict.get("company_section", "")
    company_text    = conflict.get("company_text", "")
    vendor_section  = conflict.get("vendor_section", "")
    vendor_text     = conflict.get("vendor_text", "")

    company_cell = [
        Paragraph("YOUR CONTRACT", s["label"]),
        Paragraph(company_section, s["section_ref"]),
        Paragraph(f'"{_escape(company_text)}"', s["clause_text"]),
    ]
    vendor_cell = [
        Paragraph("VENDOR CONTRACT", s["label"]),
        Paragraph(vendor_section, s["section_ref"]),
        Paragraph(f'"{_escape(vendor_text)}"', s["clause_text"]),
    ]

    clause_table = Table(
        [[company_cell, Paragraph("<b>VS</b>", ParagraphStyle("vs", fontSize=9, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER)), vendor_cell]],
        colWidths=[2.9 * inch, 0.4 * inch, 2.9 * inch],
    )
    clause_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), colors.HexColor("#F8FAFC")),
        ("BACKGROUND",    (2, 0), (2, 0), colors.HexColor("#F8FAFC")),
        ("BOX",           (0, 0), (0, 0), 0.5, colors.HexColor("#E2E8F0")),
        ("BOX",           (2, 0), (2, 0), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (1, 0), (1, 0), "CENTER"),
        ("VALIGN",        (1, 0), (1, 0), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(clause_table)

    # Explanation + Resolution
    explanation = conflict.get("conflict_explanation", "")
    resolution  = conflict.get("resolution", "")

    detail_table = Table(
        [[
            [Paragraph("WHY THIS CONFLICTS", s["label"]),
             Paragraph(_escape(explanation), s["body"])],
            [Paragraph("SUGGESTED RESOLUTION", s["label"]),
             Paragraph(_escape(resolution), s["resolution"])],
        ]],
        colWidths=[3.15 * inch, 3.15 * inch],
    )
    detail_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), colors.white),
        ("BACKGROUND",    (1, 0), (1, 0), colors.HexColor("#EEF2F7")),
        ("BOX",           (0, 0), (0, 0), 0.5, colors.HexColor("#E2E8F0")),
        ("BOX",           (1, 0), (1, 0), 0.5, colors.HexColor("#C7D7EC")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(detail_table)
    elements.append(Spacer(1, 0.18 * inch))

    return elements


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def generate_pdf(report: dict) -> bytes:
    """Generate a polished redline brief PDF and return it as bytes."""
    buf = io.BytesIO()
    s = _styles()

    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.6 * inch,
        title="ClauseGuard — Redline Brief",
        author="ClauseGuard",
    )

    title = report.get("title", "Contract Conflict Analysis")
    conflicts = report.get("conflicts", [])
    recommendation = report.get("recommendation", "")

    page_decorator = _make_page_decorator(title)
    elements = []

    # Cover
    elements += _cover(report, s)

    # Conflicts by risk order
    risk_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    sorted_conflicts = sorted(
        conflicts,
        key=lambda c: risk_order.index(c.get("risk", "LOW").upper())
        if c.get("risk", "LOW").upper() in risk_order else 4
    )

    elements.append(Paragraph("Conflict Analysis", s["section_heading"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 0.1 * inch))

    for conflict in sorted_conflicts:
        card = _conflict_card(conflict, s)
        elements.append(KeepTogether(card[:2]))  # keep header + clause table together
        elements += card[2:]

    # Recommendation footer
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0")))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("Recommendation", s["section_heading"]))
    elements.append(Paragraph(recommendation, s["recommendation"]))

    doc.build(elements, onFirstPage=page_decorator, onLaterPages=page_decorator)
    return buf.getvalue()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _escape(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _hex(color) -> str:
    """Convert a ReportLab color to a hex string without the leading #."""
    return "{:02X}{:02X}{:02X}".format(
        int(color.red * 255),
        int(color.green * 255),
        int(color.blue * 255),
    )
