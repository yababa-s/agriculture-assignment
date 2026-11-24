"""PDF tools exposed to agents: page text (with Kruti Dev decoding) and table grids."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pdfplumber
import pymupdf

from agri.tools.krutidev import has_kruti, krutidev_to_unicode, split_bilingual_label
from agri.tools.parsing import is_numeric_cell


@dataclass
class Grid:
    """A table as extracted from one page, with header rows separated from body rows."""
    page: int                      # 1-based
    index: int                     # table index on the page
    header_rows: list[list[str]]
    body_rows: list[list[str]]
    title: str = ""                # nearest caption text above the table
    col_headers: list[str] = field(default_factory=list)  # flattened header per column
    continued_from: str | None = None  # ref of the grid whose header this continuation reuses
    ruling: str = "vector"             # vector = PDF lines, raster = lines detected in a background image

    @property
    def ref(self) -> str:
        return f"p{self.page}_t{self.index}"

    def preview(self, n: int = 4) -> str:
        lines = [" | ".join(self.col_headers)]
        lines += [" | ".join(c for c in r) for r in self.body_rows[:n]]
        return "\n".join(lines)


@lru_cache(maxsize=32)
def page_texts(path: str) -> tuple[str, ...]:
    with pymupdf.open(path) as doc:
        return tuple(p.get_text() for p in doc)


def page_text_unicode(path: str, page: int) -> str:
    """Page text with Kruti Dev runs converted to Devanagari where the page uses the legacy font."""
    t = page_texts(path)[page - 1]
    if not has_kruti(t):
        return t
    out = []
    for line in t.splitlines():
        hi, en = split_bilingual_label(line)
        out.append((hi + " " + en).strip() if hi else line)
    return "\n".join(out)


def _clean(c) -> str:
    return " ".join(str(c or "").split())


def _row_is_data(row: list[str]) -> bool:
    nums = sum(1 for c in row[1:] if c and is_numeric_cell(c))
    return nums >= 2


def _flatten_headers(header_rows: list[list[str | None]], ncols: int) -> list[str]:
    """Join header rows per column. pdfplumber gives None for cells covered by a
    horizontal merge, so a None inherits the last real cell on its row."""
    filled = []
    for ri, hr in enumerate(header_rows):
        row, last = [], ""
        for i in range(ncols):
            c = hr[i] if i < len(hr) else None
            above = header_rows[ri - 1][i] if ri > 0 and i < len(header_rows[ri - 1]) else None
            if c is None and above is not None and _clean(above):
                row.append("")  # vertical merge: the cell above already names this column
            elif c is None:
                row.append(last)
            else:
                last = _clean(c)
                row.append(last)
        filled.append(row)
    out = []
    for i in range(ncols):
        parts = []
        for row in filled:
            if row[i] and (not parts or parts[-1] != row[i]):
                parts.append(row[i])
        out.append(" | ".join(parts))
    return out


def _looks_scrambled(cell) -> bool:
    """Rotated header text comes out of pdfplumber as spaced single letters ('d e r r IR e fs')."""
    toks = str(cell or "").split()
    return len(toks) >= 4 and sum(1 for t in toks if len(t) <= 2) >= 0.6 * len(toks)


def _reread_header_cells(path: str, pno: int, tbl, n_header: int, ncols: int, header_rows):
    """Re-read header cells with PyMuPDF clipped to each cell box; PyMuPDF follows text rotation."""
    out = [list(r) for r in header_rows]
    with pymupdf.open(path) as doc:
        page = doc[pno - 1]
        for ri, row in enumerate(tbl.rows[:n_header]):
            for ci, bbox in enumerate(row.cells[:ncols]):
                if bbox is None or not _looks_scrambled(out[ri][ci]):
                    continue
                txt = page.get_text("text", clip=pymupdf.Rect(*bbox))
                out[ri][ci] = " ".join(txt.split())
    return out


def raster_rules(path: str, pno: int, min_v: float = 0.08, min_h: float = 0.1):
    """Detect table ruling lines drawn inside a raster image covering the page.

    Some DES PDFs place the table grid as a scanned image under the text layer, so
    there are no vector lines. Dark pixel columns/rows of that image are the rules;
    they are mapped back to PDF coordinates for pdfplumber's explicit strategy.
    """
    import numpy as np
    with pymupdf.open(path) as doc:
        page = doc[pno - 1]
        best = None
        for img in page.get_images(full=True):
            for rect in page.get_image_rects(img[0]):
                if rect.width * rect.height > 0.3 * page.rect.width * page.rect.height:
                    best = (img[0], rect)
        if not best:
            return None
        xref, rect = best
        pix = pymupdf.Pixmap(doc, xref)
        if pix.n - pix.alpha < 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3].mean(axis=2)
        dark = arr < 128

        def groups(mask):
            idx = np.where(mask)[0]
            out, start = [], None
            for a, b in zip(idx, list(idx[1:]) + [None]):
                start = a if start is None else start
                if b is None or b != a + 1:
                    out.append((start + a) / 2)
                    start = None
            return out

        def longest_run(mask2d, axis):
            """Longest run of consecutive dark pixels along each row (axis=1) or column (axis=0).
            Ruling lines are long unbroken runs; text rows are dark too but broken into short strokes."""
            m = mask2d if axis == 1 else mask2d.T
            best = np.zeros(m.shape[0], dtype=np.int32)
            cur = np.zeros(m.shape[0], dtype=np.int32)
            for col in range(m.shape[1]):
                cur = np.where(m[:, col], cur + 1, 0)
                best = np.maximum(best, cur)
            return best

        vx = groups(longest_run(dark, 0) > min_v * dark.shape[0])
        hy = groups(longest_run(dark, 1) > min_h * dark.shape[1])
        if len(vx) < 3 or len(hy) < 3:
            return None

        def segments(line_px, along_axis):
            """Where a detected rule is actually drawn: runs of dark pixels along it (merged header
            cells have no rule between their columns, so full-length lines would split them)."""
            c = int(round(line_px))
            band = dark[:, max(0, c - 1):c + 2].any(axis=1) if along_axis == 0 else dark[max(0, c - 1):c + 2, :].any(axis=0)
            min_seg = max(8, int(0.004 * band.size))
            out, start, gap = [], None, 0
            for i, v in enumerate(list(band) + [False] * 5):   # sentinel closes a run that reaches the edge
                if v:
                    start = i if start is None else start
                    gap = 0
                elif start is not None:
                    gap += 1
                    if gap > 3:                      # tolerate tiny breaks in a scanned line
                        if i - gap - start + 1 >= min_seg:
                            out.append((start, i - gap))
                        start, gap = None, 0
            return out

        sx_, sy_ = rect.width / pix.width, rect.height / pix.height
        vsegs, hsegs = [], []
        for x in vx:
            X = rect.x0 + x * sx_
            for a, b in segments(x, 0):
                top, bottom = rect.y0 + a * sy_, rect.y0 + b * sy_
                vsegs.append({"object_type": "line", "x0": X, "x1": X, "top": top, "bottom": bottom,
                              "width": 0, "height": bottom - top})
        for y in hy:
            Y = rect.y0 + y * sy_
            for a, b in segments(y, 1):
                x0, x1 = rect.x0 + a * sx_, rect.x0 + b * sx_
                hsegs.append({"object_type": "line", "x0": x0, "x1": x1, "top": Y, "bottom": Y,
                              "width": x1 - x0, "height": 0})
        return vsegs, hsegs


def extract_grids(path: str, pages: list[int] | None = None) -> list[Grid]:
    grids: list[Grid] = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            if pages and pno not in pages:
                continue
            tables = page.find_tables()
            ruling = "vector"
            if not tables:
                rules = raster_rules(path, pno)
                if rules:
                    xs, ys = rules
                    tables = page.find_tables({"vertical_strategy": "explicit", "horizontal_strategy": "explicit",
                                               "explicit_vertical_lines": xs, "explicit_horizontal_lines": ys})
                    ruling = "raster"
            for ti, tbl in enumerate(tables):
                raw = tbl.extract()
                if not raw or len(raw) < 2:
                    continue
                ncols = max(len(r) for r in raw)
                raw = [list(r) + [None] * (ncols - len(r)) for r in raw]
                first_data = next((i for i, r in enumerate(raw) if _row_is_data([_clean(c) for c in r])), None)
                if first_data is None:
                    continue
                if ruling == "raster":
                    # an explicit grid splits merged header cells into empty ones: let them inherit from the left
                    raw[:first_data] = [[None if (c is not None and not _clean(c)) else c for c in h] for h in raw[:first_data]]
                if any(_looks_scrambled(c) for h in raw[:first_data] for c in h):
                    raw[:first_data] = _reread_header_cells(path, pno, tbl, first_data, ncols, raw[:first_data])
                header, lead_body = [], []
                for h in raw[:first_data]:
                    cells = [_clean(c) for c in h]
                    filled = [c for c in cells if c]
                    if all(c.isdigit() or not c for c in cells):
                        continue  # "1 2 3 4 ..." column-number row
                    if len(filled) == 1 and filled[0] in cells[:2] and len(cells) > 3:
                        lead_body.append(cells)  # section row such as "Cereals" sits above the first data row
                        continue
                    header.append(h)
                body = lead_body + [[_clean(c) for c in r] for r in raw[first_data:]]
                header_blank = not any(_clean(c) for h in header for c in h)
                prev = grids[-1] if grids else None
                if header_blank and prev and len(prev.col_headers) == ncols and prev.page in (pno, pno - 1):
                    # table continues from the previous page: reuse its header
                    g = Grid(page=pno, index=ti, header_rows=prev.header_rows, body_rows=body,
                             title=prev.title, col_headers=prev.col_headers, continued_from=prev.ref, ruling=ruling)
                    grids.append(g)
                    continue
                # caption: text just above the table bbox
                top = tbl.bbox[1]
                cap_box = (0, max(0, top - 60), page.width, top)
                try:
                    title = _clean(page.crop(cap_box).extract_text())
                except ValueError:
                    title = ""
                g = Grid(page=pno, index=ti, header_rows=[[c if c is None else _clean(c) for c in h] for h in header],
                         body_rows=body, title=title, ruling=ruling)
                g.col_headers = _flatten_headers(g.header_rows, ncols)
                grids.append(g)
    return grids


def decode_bilingual(cell: str, legacy_font: bool) -> tuple[str, str]:
    """(hindi_unicode, english) for a cell. Only documents flagged as Kruti Dev are decoded,
    otherwise English words missing from the dictionary would be misread as Hindi."""
    if not cell:
        return "", ""
    if not legacy_font:
        deva = [t for t in cell.split() if any("\u0900" <= ch <= "\u097f" for ch in t)]
        latin = [t for t in cell.split() if t not in deva and any(ch.isalpha() for ch in t)]
        if deva and latin:   # Unicode bilingual label, e.g. OCR of a DES table: "धान Paddy"
            return " ".join(deva), " ".join(t for t in cell.split() if t not in deva)
        return "", cell
    return split_bilingual_label(cell)


def pdf_page_count(path: str | Path) -> int:
    with pymupdf.open(str(path)) as d:
        return len(d)

