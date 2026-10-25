"""Export USAGE_GUIDE.md to USAGE_GUIDE.pdf (shareable)."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "USAGE_GUIDE.md"
PDF_PATH = ROOT / "USAGE_GUIDE.pdf"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inline_md(text: str) -> str:
    """Very small markdown inline converter for ReportLab Paragraph XML."""
    text = _escape(text)
    text = re.sub(r"`([^`]+)`", r"<font face='Courier' size='9'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<link href='\2' color='blue'>\1</link>", text)
    return text


def build_pdf() -> Path:
    md = MD_PATH.read_text(encoding="utf-8")
    # Fix common mojibake if PowerShell rewrote the file
    md = md.replace("â†’", "->").replace("â€¦", "...").replace("\ufeff", "")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "GuideTitle",
        parent=styles["Title"],
        fontSize=20,
        textColor=colors.HexColor("#1e3a5f"),
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=colors.HexColor("#1e3a5f"),
        spaceBefore=16,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#2c5282"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    code_style = ParagraphStyle(
        "CodeBlock",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8,
        leading=11,
        backColor=colors.HexColor("#f4f6f8"),
        leftIndent=6,
        rightIndent=6,
        spaceBefore=4,
        spaceAfter=8,
    )
    bullet_style = ParagraphStyle(
        "BulletBody",
        parent=body,
        leftIndent=12,
        bulletIndent=0,
    )

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="DataWise Usage Guide",
        author="DataWise",
    )

    story = []
    lines = md.splitlines()
    i = 0
    first_h1_done = False

    while i < len(lines):
        line = lines[i].rstrip()

        if not line.strip():
            i += 1
            continue

        if line.strip() == "---":
            story.append(Spacer(1, 8))
            i += 1
            continue

        # Fenced code block
        if line.strip().startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # closing fence
            block = "\n".join(code_lines) if code_lines else ""
            story.append(Preformatted(block, code_style))
            continue

        # Table
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            table_rows = []
            while i < len(lines) and "|" in lines[i]:
                raw = lines[i].strip()
                if re.match(r"^\|?\s*:?-{3,}", raw):
                    i += 1
                    continue
                cells = [c.strip() for c in raw.strip("|").split("|")]
                table_rows.append([Paragraph(_inline_md(c), body) for c in cells])
                i += 1
            if table_rows:
                col_count = max(len(r) for r in table_rows)
                for r in table_rows:
                    while len(r) < col_count:
                        r.append(Paragraph("", body))
                usable = letter[0] - 1.5 * inch
                col_w = usable / col_count
                t = Table(table_rows, colWidths=[col_w] * col_count, repeatRows=1)
                t.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e0")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                story.append(t)
                story.append(Spacer(1, 8))
            continue

        # Headings
        if line.startswith("# "):
            text = line[2:].strip()
            if not first_h1_done:
                story.append(Paragraph(_inline_md(text), title_style))
                first_h1_done = True
            else:
                story.append(Paragraph(_inline_md(text), h1))
            i += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(_inline_md(line[3:].strip()), h1))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(_inline_md(line[4:].strip()), h2))
            i += 1
            continue

        # Bullets / numbered
        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < len(lines) and (
                re.match(r"^\s*[-*]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])
            ):
                item_text = re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]).strip()
                items.append(ListItem(Paragraph(_inline_md(item_text), bullet_style), leftIndent=10))
                i += 1
            story.append(ListFlowable(items, bulletType="bullet", start="•"))
            story.append(Spacer(1, 4))
            continue

        # Plain paragraph (merge wrapped lines lightly)
        para = line.strip()
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].strip().startswith("```") and "|" not in lines[i] and lines[i].strip() != "---" and not re.match(r"^\s*[-*]\s+", lines[i]) and not re.match(r"^\s*\d+\.\s+", lines[i]):
            para += " " + lines[i].strip()
            i += 1
        story.append(Paragraph(_inline_md(para), body))

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(0.75 * inch, 0.4 * inch, "DataWise — Usage Guide")
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.4 * inch, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return PDF_PATH


if __name__ == "__main__":
    out = build_pdf()
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
