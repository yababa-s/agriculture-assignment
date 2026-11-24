"""Build robustness test documents of the kinds an evaluator may hand over.

Each is made from a corpus page, so the correct values are already known (they are in the
knowledge base from the original digital file). None of them is used for training.

  T1 scan_area_production_2025-26.pdf   : D02 printed and scanned at 200 dpi (image-only PDF, English)
  T2 photo_prices_jan2024.png            : D12 page 1 as a PNG photo of a price table
  T3 hindi_area_production_2025-26.pdf  : D02 values re-typeset as a Unicode Hindi table (digital)
  T4 scan_basic_statistics_2024-25.pdf  : D06 page 1 scanned (bilingual Hindi + English, image-only)
  T5 map_india_lulc.png                  : D19 map as a PNG (should be skipped as a map)
  T6 hindi_broken_textlayer_2025-26.pdf : T3's table typeset with shaping; its text layer garbles Hindi
                                          conjuncts (a common defect in real Hindi PDFs)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from agri import config  # noqa: E402

OUT = config.ROOT / "data" / "test_unseen"
C = config.CORPUS_DIR


def scan(src: Path, dst: Path, pages: list[int] | None = None, dpi: int = 200) -> None:
    s = pymupdf.open(src)
    o = pymupdf.open()
    for i in (pages or range(1, len(s) + 1)):
        p = s[i - 1]
        np_ = o.new_page(width=p.rect.width, height=p.rect.height)
        np_.insert_image(np_.rect, stream=p.get_pixmap(dpi=dpi).tobytes("png"))
    o.save(dst, garbage=3, deflate=True)


def png(src: Path, dst: Path, page: int = 1, dpi: int = 200) -> None:
    pymupdf.open(src)[page - 1].get_pixmap(dpi=dpi).save(dst)


CROPS_HI = [("paddy", "धान"), ("maize", "मक्का"), ("green_gram", "मूंग"), ("black_gram", "उड़द"),
            ("black_pepper", "काली मिर्च"), ("ginger", "अदरक"), ("turmeric", "हल्दी"), ("arecanut", "सुपारी"),
            ("banana", "केला"), ("mango", "आम"), ("papaya", "पपीता"), ("guava", "अमरूद")]
ZONES_HI = [("ZN_DIGLIPUR", "दिगलीपुर"), ("ZN_MAYABUNDER", "मायाबंदर"), ("ZN_RANGAT", "रंगत"),
            ("ZN_SOUTHANDAMAN", "दक्षिण अंडमान"), ("ZN_CARNICOBAR", "कार निकोबार"), ("AN", "अंडमान और निकोबार द्वीपसमूह")]


def hindi_table(dst: Path) -> None:
    conn = sqlite3.connect(config.DB_PATH)

    def val(cid, loc, metric):
        r = conn.execute("SELECT value_raw FROM observation WHERE document_id='D02' AND commodity_id=? AND location_id=? "
                         "AND metric_id=? AND period_label='2025-26'", (cid, loc, metric)).fetchone()
        return r[0] if r and r[0] else "-"
    head1 = "".join(f'<th colspan="2">{z}</th>' for _, z in ZONES_HI)
    head2 = "<th>फसल</th>" + "<th>क्षेत्रफल</th><th>उत्पादन</th>" * len(ZONES_HI)
    rows = "".join("<tr><td>" + hi + "</td>" + "".join(f"<td>{val(cid, z, 'area_cultivated')}</td><td>{val(cid, z, 'production')}</td>"
                                                          for z, _ in ZONES_HI) + "</tr>" for cid, hi in CROPS_HI)
    html = (f"<h3>क्षेत्रफल एवं उत्पादन 2025-26</h3><p>क्षेत्रफल हेक्टेयर में, उत्पादन मीट्रिक टन में</p>"
            f"<table><tr><th></th>{head1}</tr><tr>{head2}</tr>{rows}</table>")
    css = ('@font-face {font-family: uni; src: url("Arial Unicode.ttf");} body {font-family: uni; font-size: 8pt;} '
           'table {border-collapse: collapse;} td, th {border: 1px solid black; padding: 2pt; font-size: 7pt;}')
    story = pymupdf.Story(html=html, user_css=css, archive=pymupdf.Archive("/System/Library/Fonts/Supplemental"))
    tmp = dst.with_suffix(".tmp.pdf")
    w = pymupdf.DocumentWriter(str(tmp))
    page = pymupdf.paper_rect("a4-l")
    more = 1
    while more:
        dev = w.begin_page(page)
        more, _ = story.place(page + (30, 30, -30, -30))
        story.draw(dev)
        w.end_page()
    w.close()
    d = pymupdf.open(tmp)
    d.subset_fonts()
    d.save(dst, garbage=3, deflate=True)
    tmp.unlink()


def hindi_table_clean(dst: Path) -> None:
    """Same table drawn cell by cell: the text layer holds exact Unicode (no shaping, so conjuncts look
    plain on screen, but every character extracts correctly, as in well-made government PDFs)."""
    conn = sqlite3.connect(config.DB_PATH)

    def val(cid, loc, metric):
        r = conn.execute("SELECT value_raw FROM observation WHERE document_id='D02' AND commodity_id=? AND location_id=? "
                         "AND metric_id=? AND period_label='2025-26'", (cid, loc, metric)).fetchone()
        return r[0] if r and r[0] else "-"
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    font = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    page.insert_font(fontname="uni", fontfile=font)
    page.insert_text((30, 40), "क्षेत्रफल एवं उत्पादन 2025-26", fontname="uni", fontsize=12)
    page.insert_text((30, 58), "क्षेत्रफल हेक्टेयर में, उत्पादन मीट्रिक टन में", fontname="uni", fontsize=9)
    x0, y, label_w, cw, rh = 30, 70, 70, 60, 16
    cols = len(ZONES_HI) * 2

    def cell(x, y_, w, text):
        page.draw_rect(pymupdf.Rect(x, y_, x + w, y_ + rh), color=(0, 0, 0), width=0.6)
        if text:
            page.insert_text((x + 3, y_ + rh - 4), text, fontname="uni", fontsize=7)
    cell(x0, y, label_w, "")
    for i, (_, z) in enumerate(ZONES_HI):
        cell(x0 + label_w + 2 * i * cw, y, 2 * cw, z)
    y += rh
    cell(x0, y, label_w, "फसल")
    for i in range(cols):
        cell(x0 + label_w + i * cw, y, cw, "क्षेत्रफल" if i % 2 == 0 else "उत्पादन")
    for cid, hi in CROPS_HI:
        y += rh
        cell(x0, y, label_w, hi)
        for i, (z, _) in enumerate(ZONES_HI):
            cell(x0 + label_w + 2 * i * cw, y, cw, val(cid, z, "area_cultivated"))
            cell(x0 + label_w + (2 * i + 1) * cw, y, cw, val(cid, z, "production"))
    doc.subset_fonts()
    doc.save(dst, garbage=3, deflate=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scan(C / "Area and Production/47-Area and Production 2025-26.pdf", OUT / "scan_area_production_2025-26.pdf")
    png(C / "Market Price Analysis/Fooditems2024.pdf", OUT / "photo_prices_jan2024.png")
    hindi_table_clean(OUT / "hindi_area_production_2025-26.pdf")
    hindi_table(OUT / "hindi_broken_textlayer_2025-26.pdf")
    scan(C / "Basic Statistics/Year 2024-25.pdf", OUT / "scan_basic_statistics_2024-25.pdf", pages=[1])
    png(C / "SAT Bhuvan Data/Map of India LULC 2024-25.pdf", OUT / "map_india_lulc.png", dpi=100)
    for f in sorted(OUT.iterdir()):
        print(f"{f.stat().st_size // 1024:>6} KB  {f.name}")


if __name__ == "__main__":
    main()
