"""Helpers to fill the course PowerPoint templates in place: keep every shape, style and position; replace the
bracketed placeholder text, fill tables, and drop figures/videos into the 'Visual placeholder' boxes."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

RED = {"B03A2E", "C00000", "FF0000", "B4312A"}


def _clean_rpr(rpr):
    """Remove placeholder-red colour from a run's properties."""
    if rpr is None:
        return None
    rpr = copy.deepcopy(rpr)
    for sf in rpr.findall(qn("a:solidFill")):
        clr = sf.find(qn("a:srgbClr"))
        if clr is not None and clr.get("val", "").upper() in RED:
            rpr.remove(sf)
    return rpr


def set_lines(shape, lines: list[str], size: float | None = None, color: str | None = None, bold_first: bool = False):
    """Replace a shape's text with `lines`, reusing the formatting of the first run of each source paragraph.
    Inline **bold** is supported."""
    tf = shape.text_frame
    src_ps = list(tf.paragraphs)
    p_tmpl = [copy.deepcopy(p._p.pPr) if p._p.pPr is not None else None for p in src_ps]
    r_tmpl = []
    for p in src_ps:
        r = p.runs[0]._r.rPr if p.runs and p.runs[0]._r.rPr is not None else None
        r_tmpl.append(_clean_rpr(r))
    txBody = tf._txBody
    for p in list(txBody.findall(qn("a:p"))):
        txBody.remove(p)
    for i, line in enumerate(lines):
        k = min(i, len(src_ps) - 1)
        p = etree.SubElement(txBody, qn("a:p"))
        if p_tmpl[k] is not None:
            p.append(copy.deepcopy(p_tmpl[k]))
        for j, part in enumerate(re.split(r"(\*\*.+?\*\*)", line)):
            if not part:
                continue
            r = etree.SubElement(p, qn("a:r"))
            rpr = copy.deepcopy(r_tmpl[k]) if r_tmpl[k] is not None else etree.Element(qn("a:rPr"))
            rpr.set("lang", "en-IN")
            if part.startswith("**") or (bold_first and i == 0):
                rpr.set("b", "1")
            if size:
                rpr.set("sz", str(int(size * 100)))
            if color:
                for sf in rpr.findall(qn("a:solidFill")):
                    rpr.remove(sf)
                sf = etree.SubElement(rpr, qn("a:solidFill"))
                etree.SubElement(sf, qn("a:srgbClr")).set("val", color)
                rpr.insert(0, sf)
            r.append(rpr)
            t = etree.SubElement(r, qn("a:t"))
            t.text = part[2:-2] if part.startswith("**") else part
    return shape


def by_name(slide, name: str, nth: int = 0):
    hits = [s for s in slide.shapes if s.name == name]
    return hits[nth] if len(hits) > nth else None


def text_shape(slide, startswith: str):
    for s in slide.shapes:
        if s.has_text_frame and s.text_frame.text.strip().startswith(startswith):
            return s
    return None


def remove(shape):
    if shape is not None:
        shape._element.getparent().remove(shape._element)


def fill_table(shape, rows: list[list], size: float | None = None, header: list[str] | None = None):
    """Set the table to len(rows) data rows (cloning the last template row as needed) and fill every cell."""
    tbl = shape.table
    trs = tbl._tbl.findall(qn("a:tr"))
    body_tmpl = trs[-1]
    for tr in trs[1:]:
        tbl._tbl.remove(tr)
    for _ in rows:
        tbl._tbl.append(copy.deepcopy(body_tmpl))
    if header:
        for j, h in enumerate(header):
            _cell(tbl.cell(0, j), str(h), size)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row):
            _cell(tbl.cell(i, j), "" if v is None else str(v), size)
    # keep total height reasonable: shrink row heights
    for tr in tbl._tbl.findall(qn("a:tr")):
        tr.set("h", str(int(Emu(Pt(18)))))


def _cell(cell, text: str, size: float | None):
    tf = cell.text_frame
    p0 = tf.paragraphs[0]
    rpr = p0.runs[0]._r.rPr if p0.runs and p0.runs[0]._r.rPr is not None else None
    rpr = _clean_rpr(rpr)
    for p in list(tf._txBody.findall(qn("a:p")))[1:]:
        tf._txBody.remove(p)
    for r in list(p0._p.findall(qn("a:r"))):
        p0._p.remove(r)
    r = etree.SubElement(p0._p, qn("a:r"))
    rp = copy.deepcopy(rpr) if rpr is not None else etree.Element(qn("a:rPr"))
    if size:
        rp.set("sz", str(int(size * 100)))
    r.append(rp)
    t = etree.SubElement(r, qn("a:t"))
    t.text = text
    end = p0._p.find(qn("a:endParaRPr"))
    if end is not None:
        p0._p.remove(end)
        p0._p.append(end)


def fit_picture(slide, box, path: Path, pad: float = 0.05):
    """Insert an image inside the box (keeping aspect ratio, centred)."""
    w, h = Image.open(path).size
    bw, bh = box.width * (1 - 2 * pad), box.height * (1 - 2 * pad)
    scale = min(bw / w, bh / h)
    pw, ph = int(w * scale), int(h * scale)
    left = box.left + (box.width - pw) // 2
    top = box.top + (box.height - ph) // 2
    return slide.shapes.add_picture(str(path), left, top, pw, ph)


def fit_movie(slide, box, mp4: Path, poster: Path, pad: float = 0.04):
    w, h = Image.open(poster).size
    bw, bh = box.width * (1 - 2 * pad), box.height * (1 - 2 * pad)
    scale = min(bw / w, bh / h)
    pw, ph = int(w * scale), int(h * scale)
    return slide.shapes.add_movie(str(mp4), box.left + (box.width - pw) // 2, box.top + (box.height - ph) // 2, pw, ph,
                                  poster_frame_image=str(poster), mime_type="video/mp4")


def presenter(slide, text: str):
    s = text_shape(slide, "Presenter:")
    if s:
        set_lines(s, [text])


_ = (RGBColor,)
