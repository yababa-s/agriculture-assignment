"""Show the source page of any stored number, with the printed cell highlighted.

The observation keeps document, page, row label, column label and the printed text. The page is
rendered with PyMuPDF; the printed text is searched on that page and, when it occurs more than once,
the hit closest to the row label (vertically) and the column label (horizontally) is chosen.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from agri import config


def _anchor(page, label: str | None):
    """First word of a label that can be found on the page (labels may hold decoded Hindi)."""
    for tok in (label or "").replace("|", " ").split():
        tok = tok.strip("*().,:")
        if len(tok) >= 3 and tok.isascii():
            hits = page.search_for(tok)
            if hits:
                return hits[0]
    return None


def render_source(conn: sqlite3.Connection, obs_id: int, out_dir: Path | None = None, zoom: float = 2.0) -> dict:
    import pymupdf
    r = conn.execute("""SELECT o.obs_id, o.document_id, o.page, o.value_raw, o.row_label, o.col_label, o.value, o.unit_id,
                               d.relative_path, d.file_name, d.modality
                        FROM observation o JOIN document d ON d.document_id=o.document_id WHERE o.obs_id=?""",
                     (obs_id,)).fetchone()
    if not r:
        raise ValueError(f"observation {obs_id} not found")
    out_dir = out_dir or (config.ROOT / "outputs" / "provenance")
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Path(r["relative_path"]) if Path(r["relative_path"]).is_absolute() else config.CORPUS_DIR / r["relative_path"]
    if not src.exists():
        raise FileNotFoundError(f"{src} not found. Fetch the corpus: python scripts/fetch_artifacts.py --only corpus")
    out = out_dir / f"obs_{obs_id}_{r['document_id']}_p{r['page']}.png"
    if src.suffix.lower() in (".png", ".jpg", ".jpeg"):
        shutil.copy(src, out)
        return {"image": str(out), "highlighted": False, "document_id": r["document_id"], "page": r["page"],
                "note": "image source: shown whole (cell positions are not stored for OCR images)"}
    doc = pymupdf.open(src)
    page = doc[(r["page"] or 1) - 1]
    hits = page.search_for(str(r["value_raw"]).strip())
    row_a, col_a = _anchor(page, r["row_label"]), _anchor(page, r["col_label"])
    chosen = None
    if hits:
        def dist(h):
            dy = abs(((h.y0 + h.y1) / 2) - ((row_a.y0 + row_a.y1) / 2)) if row_a else 0
            dx = abs(((h.x0 + h.x1) / 2) - ((col_a.x0 + col_a.x1) / 2)) if col_a else 0
            return dy * 3 + dx
        chosen = min(hits, key=dist)
        annot = page.add_rect_annot(chosen + (-3, -2, 3, 2))
        annot.set_colors(stroke=(0.85, 0.1, 0.1))
        annot.set_border(width=2.5)
        annot.update()
        if row_a:
            hl = page.add_highlight_annot(row_a)
            hl.update()
    page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(out)
    return {"image": str(out), "highlighted": chosen is not None, "document_id": r["document_id"], "page": r["page"],
            "file_name": r["file_name"], "printed": r["value_raw"], "matches_on_page": len(hits)}
