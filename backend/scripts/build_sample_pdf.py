"""Build data/samples/regulamento-teletrabalho.pdf from its Markdown source.

The PDF is committed, so this only needs to run when the source changes:

    uv run python scripts/build_sample_pdf.py

Each chapter starts on a new page, and chapters and articles become PDF bookmarks, so the demo
exercises page numbers and outline-based headings.
"""

from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
SOURCE = SAMPLES / "sources" / "regulamento-teletrabalho.md"
TARGET = SAMPLES / "regulamento-teletrabalho.pdf"


def latin1(text: str) -> str:
    # The built-in PDF fonts only cover Latin-1; Portuguese letters are fine, dashes are not.
    return text.replace("\u2014", "-").replace("\u2019", "'")  # em dash, right quote


def build() -> None:
    pdf = FPDF(format="A4")
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_title("Regulamento Interno de Teletrabalho")
    pdf.set_author("Aurora Tech, Lda. (fictional)")
    pdf.set_creation_date(datetime(2026, 3, 1, tzinfo=UTC))  # reproducible output

    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        line = latin1(raw.strip())
        if not line:
            continue
        if line.startswith("# "):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 9, line[2:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
        elif line.startswith("## "):
            pdf.add_page()
            pdf.start_section(line[3:], level=0)
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 8, line[3:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        elif line.startswith("### "):
            pdf.start_section(line[4:], level=1)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, line[4:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

    pdf.output(str(TARGET))
    print(f"Wrote {TARGET} ({pdf.page} pages)")


if __name__ == "__main__":
    build()
