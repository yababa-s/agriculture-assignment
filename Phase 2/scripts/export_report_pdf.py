"""Render docs/interim_report.md to a PDF (docs/<TEAM>_AN_interim_report_v1.pdf) with PyMuPDF's HTML engine.

  ./.venv/bin/python scripts/export_report_pdf.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import markdown  # noqa: E402
import pymupdf  # noqa: E402

from agri import config  # noqa: E402

UNICODE_FONT_DIR = "/System/Library/Fonts/Supplemental"   # Arial Unicode covers Devanagari on macOS
CSS = """
@font-face { font-family: uni; src: url("Arial Unicode.ttf"); }
body { font-family: sans-serif, uni; font-size: 10pt; line-height: 1.4; color: #1a2233; }
h1 { font-size: 18pt; color: #14213D; margin-bottom: 4pt; }
h2 { font-size: 13pt; color: #14213D; border-bottom: 1px solid #c8c2b2; padding-bottom: 2pt; margin-top: 14pt; }
h3 { font-size: 11pt; color: #2E7D5B; }
p, li { font-size: 10pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; }
th { color: #14213D; font-weight: bold; font-size: 9pt; padding: 3pt; text-align: left; border-bottom: 2px solid #14213D; }
td { border: 1px solid #d9d4c7; font-size: 9pt; padding: 3pt; }
code { font-family: monospace; font-size: 9pt; }
a { color: #2E7D5B; text-decoration: none; }
"""


def _normalise(md: str) -> str:
    """Python-Markdown needs 4-space nested lists and a blank line before a list; GitHub does not."""
    out: list[str] = []
    for line in md.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        is_item = stripped[:2] in ("* ", "- ") or (stripped[:1].isdigit() and ". " in stripped[:4])
        if is_item and indent:
            line = " " * (indent * 2) + stripped
        if is_item and out and out[-1].strip() and not _is_item(out[-1]):
            out.append("")
        out.append(line)
    return "\n".join(out).replace("\nCS F/U", "  \nCS F/U")


def _is_item(line: str) -> bool:
    s = line.lstrip(" ")
    return s[:2] in ("* ", "- ") or (s[:1].isdigit() and ". " in s[:4])


def main() -> None:
    src = config.ROOT / "docs" / "interim_report.md"
    out = config.ROOT / "docs" / f"{config.TEAM_ID}_{config.STATE}_interim_report_v1.pdf"
    html = markdown.markdown(_normalise(src.read_text()), extensions=["tables", "fenced_code"])
    # MuPDF repeats <thead> rows across page breaks and paints them over later content; use plain rows
    for tag in ("<thead>", "</thead>", "<tbody>", "</tbody>"):
        html = html.replace(tag, "")
    story = pymupdf.Story(html=html, user_css=CSS, archive=pymupdf.Archive(UNICODE_FONT_DIR))
    writer = pymupdf.DocumentWriter(str(out))
    page = pymupdf.paper_rect("a4")
    body = page + (54, 54, -54, -54)
    more, n = 1, 0
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(body)
        story.draw(dev)
        writer.end_page()
        n += 1
    writer.close()
    # page numbers in the footer
    doc = pymupdf.open(str(out))
    for i, p in enumerate(doc, start=1):
        p.insert_text((page.width / 2 - 30, page.height - 28), f"Team 34 · page {i} of {len(doc)}", fontsize=8, color=(0.4, 0.43, 0.5))
    doc.saveIncr()
    print(f"{n} pages -> {out}")


if __name__ == "__main__":
    main()
