"""Small helper layer over python-docx that writes into the course templates' styles.

The template file is opened, its body is emptied (guidance page and green boxes removed) and the
section properties, header, footer and styles are kept; content is then written in template order.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HEAD_FILL, BORDER, HEAD_INK = "DCE8D2", "B7C4B0", "1F3A1F"


class Doc:
    def __init__(self, template: Path, header_map: dict[str, str]):
        self.d = Document(str(template))
        body = self.d.element.body
        for el in list(body):
            if el.tag != qn("w:sectPr"):
                body.remove(el)
        for sec in self.d.sections:
            for part in (sec.header, sec.footer):
                for p in part.paragraphs:
                    for r in p.runs:
                        for k, v in header_map.items():
                            r.text = r.text.replace(k, v)
                    # placeholders may be red in the template
                    for r in p.runs:
                        r.font.color.rgb = None
        self.fig_n = 0
        self.tab_n = 0

    # ------------------------------------------------------------ text
    def _runs(self, p, text: str, size: float | None = None, color: str | None = None):
        """**bold**, *italic*, `code` inline markup."""
        for part in re.split(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+?`)", text):
            if not part:
                continue
            if part.startswith("**"):
                r = p.add_run(part[2:-2])
                r.bold = True
            elif part.startswith("`"):
                r = p.add_run(part[1:-1])
                r.font.name = "Consolas"
                r.font.size = Pt((size or 11) - 1)
            elif part.startswith("*"):
                r = p.add_run(part[1:-1])
                r.italic = True
            else:
                r = p.add_run(part)
            if size and not part.startswith("`"):
                r.font.size = Pt(size)
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
        return p

    def para(self, text: str, size: float | None = None, align=None, after: int = 6, color: str | None = None, italic=False):
        p = self.d.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(after)
        pf.line_spacing = 1.15
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "justify":
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self._runs(p, text, size, color)
        if italic:
            for r in p.runs:
                r.italic = True
        return p

    def _styled(self, text: str, style_id: str):
        p = self.d.add_paragraph()
        ps = OxmlElement("w:pStyle")
        ps.set(qn("w:val"), style_id)
        p._p.get_or_add_pPr().insert(0, ps)
        p.add_run(text)
        if style_id.startswith("Heading"):
            p.paragraph_format.keep_with_next = True
        return p

    def title(self, text: str):
        return self._styled(text, "Title")

    def h1(self, text: str):
        return self._styled(text, "Heading1")

    def h2(self, text: str):
        return self._styled(text, "Heading2")

    def h3(self, text: str):
        return self._styled(text, "Heading3")

    def bullets(self, items: list[str], numbered: bool = False, size: float | None = None):
        for i, it in enumerate(items, 1):
            p = self._styled("", "ListParagraph")
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.5)
            self._runs(p, (f"{i}. " if numbered else "• ") + it, size)

    def code(self, text: str, size: float = 8.5):
        for line in text.splitlines() or [""]:
            p = self.d.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.left_indent = Cm(0.4)
            r = p.add_run(line if line else " ")
            r.font.name = "Consolas"
            r.font.size = Pt(size)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "F3F3F3")
            p._p.get_or_add_pPr().append(shd)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def page_break(self):
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ------------------------------------------------------------ figures / tables
    def figure(self, path: Path, caption: str, width_cm: float = 16.0):
        self.fig_n += 1
        p = self.d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(path), width=Cm(width_cm))
        c = self.d.add_paragraph()
        c.paragraph_format.space_after = Pt(10)
        r = c.add_run(f"Figure {self.fig_n}. ")
        r.bold = True
        r.font.size = Pt(9.5)
        self._runs(c, caption, 9.5)
        return self.fig_n

    def table(self, caption: str | None, headers: list[str], rows: list[list], widths_cm: list[float] | None = None,
              size: float = 9.0, bold_last: bool = False, label: str | None = None):
        if caption:
            if label is None:
                self.tab_n += 1
            c = self.d.add_paragraph()
            c.paragraph_format.keep_with_next = True
            c.paragraph_format.space_before = Pt(8)
            c.paragraph_format.space_after = Pt(4)
            r = c.add_run(f"Table {label or self.tab_n}. ")
            r.bold = True
            r.font.size = Pt(9.5)
            r2 = c.add_run(caption)
            r2.bold = True
            r2.font.size = Pt(9.5)
        t = self.d.add_table(rows=1 + len(rows), cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for j, h in enumerate(headers):
            self._cell(t.cell(0, j), str(h), size, header=True)
        for i, row in enumerate(rows, 1):
            for j, v in enumerate(row):
                self._cell(t.cell(i, j), "" if v is None else str(v), size, bold=bold_last and i == len(rows))
        if widths_cm:
            for row in t.rows:
                for j, w in enumerate(widths_cm):
                    row.cells[j].width = Cm(w)
        tr = t.rows[0]._tr
        trPr = tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        trPr.append(th)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def _cell(self, cell, text: str, size: float, header: bool = False, bold: bool = False):
        tcPr = cell._tc.get_or_add_tcPr()
        borders = OxmlElement("w:tcBorders")
        for side in ("top", "left", "bottom", "right"):
            b = OxmlElement(f"w:{side}")
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), "4")
            b.set(qn("w:color"), BORDER)
            borders.append(b)
        tcPr.append(borders)
        if header:
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), HEAD_FILL)
            tcPr.append(shd)
        mar = OxmlElement("w:tcMar")
        for side, w in (("top", 40), ("left", 80), ("bottom", 40), ("right", 80)):
            m = OxmlElement(f"w:{side}")
            m.set(qn("w:w"), str(w))
            m.set(qn("w:type"), "dxa")
            mar.append(m)
        tcPr.append(mar)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        self._runs(p, text, size)
        for r in p.runs:
            if header or bold:
                r.bold = True
            if header:
                r.font.color.rgb = RGBColor.from_string(HEAD_INK)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.d.save(str(path))
        return path


_ = (copy,)
