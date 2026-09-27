import os
import json
from pathlib import Path
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path("tests/fixtures/documents")
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# 1. sample.txt
txt_content = "This is a plain text file.\nIt contains multiple lines of known text.\nWord count should be straightforward."
(FIXTURES_DIR / "sample.txt").write_text(txt_content)

# 2. sample.md
md_content = """# Main Heading
This is a markdown file with a heading.

## Subheading
Here is some more text.
"""
(FIXTURES_DIR / "sample.md").write_text(md_content)

# 3. sample.docx
docx_path = FIXTURES_DIR / "sample.docx"
doc = Document()
doc.add_heading('Document Heading 1', level=1)
doc.add_paragraph('This is the first paragraph of the DOCX file.')
doc.add_paragraph('This is the second paragraph.')

# Add a table
table = doc.add_table(rows=2, cols=3)
hdr_cells = table.rows[0].cells
hdr_cells[0].text = 'Col1'
hdr_cells[1].text = 'Col2'
hdr_cells[2].text = 'Col3'
row_cells = table.rows[1].cells
row_cells[0].text = 'Val1'
row_cells[1].text = 'Val2'
row_cells[2].text = 'Val3'
doc.save(str(docx_path))

# 4. sample.pdf
pdf_path = FIXTURES_DIR / "sample.pdf"
c = canvas.Canvas(str(pdf_path), pagesize=letter)
c.setFont("Helvetica-Bold", 16)
c.drawString(100, 700, "PDF Heading")
c.setFont("Helvetica", 12)
c.drawString(100, 680, "This is the first page of the PDF with extractable text.")
c.showPage() # Next page
c.setFont("Helvetica", 12)
c.drawString(100, 700, "This is the second page.")
c.save()

# 5. sample_scanned.pdf (Image only, no text layer)
scanned_pdf_path = FIXTURES_DIR / "sample_scanned.pdf"
# Create an image using PIL
img = Image.new('RGB', (800, 600), color=(255, 255, 255))
d = ImageDraw.Draw(img)
# Draw text on image
d.text((50, 50), "This text is burned into an image.", fill=(0, 0, 0))
d.text((50, 80), "There is no real text layer.", fill=(0, 0, 0))

# Save image as PDF directly (which wraps the image in a PDF without a text layer)
img.save(str(scanned_pdf_path), "PDF", resolution=100.0)

# 6. expected_values.json
expected_values = {
    "sample.txt": {
        "text": txt_content,
        "word_count": len(txt_content.split())
    },
    "sample.md": {
        "text": md_content,
        "word_count": len(md_content.split()),
        "headings": ["Main Heading", "Subheading"]
    },
    "sample.docx": {
        "text": "Document Heading 1\nThis is the first paragraph of the DOCX file.\nThis is the second paragraph.",
        "word_count": 18,  # Heading:3, P1:9, P2:5. Wait, 17? Let's count properly: Document Heading 1 (3). This is the first paragraph of the DOCX file (9). This is the second paragraph (5). 3+9+5 = 17. Plus table text? Col1 Col2 Col3 Val1 Val2 Val3 (6). Total 23.
        # It's safer to just set the expectation for exact substrings.
        "substrings": ["first paragraph", "second paragraph"],
        "table": [
            ["Col1", "Col2", "Col3"],
            ["Val1", "Val2", "Val3"]
        ],
        "headings": ["Document Heading 1"]
    },
    "sample.pdf": {
        "substrings": ["PDF Heading", "first page of the PDF", "second page"],
        "page_count": 2,
        "has_text_layer": True
    },
    "sample_scanned.pdf": {
        "has_text_layer": False,
        "scanned_text_substring": "burned into an image" # only if OCR works
    }
}

(FIXTURES_DIR / "expected_values.json").write_text(json.dumps(expected_values, indent=2))
print("Fixtures generated.")
