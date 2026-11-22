"""Heuristic overflow check for filled PowerPoint files: estimated text height vs. shape height."""
import math
import sys

from pptx import Presentation


def est_height(tf, width_in):
    h = 0.0
    for p in tf.paragraphs:
        size = None
        for r in p.runs:
            if r.font.size:
                size = r.font.size.pt
        size = size or 18
        chars = len(p.text) or 1
        cpl = max(1, int(width_in * 72 / (size * 0.5)))   # average glyph ≈ 0.5 em
        h += math.ceil(chars / cpl) * size * 1.2 / 72
    return h


def main(path):
    prs = Presentation(path)
    for i, s in enumerate(prs.slides, 1):
        for sh in s.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                w, hgt = sh.width / 914400, sh.height / 914400
                e = est_height(sh.text_frame, w - 0.2)
                if e > hgt * 1.05 and hgt > 0.3:
                    print(f"slide {i:>2} {sh.name:<10} box {w:.1f}x{hgt:.1f} in, text ≈ {e:.1f} in  OVER  | {sh.text_frame.text[:60]!r}")
            if sh.has_table:
                rows = len(sh.table.rows)
                top = sh.top / 914400
                est = 0
                for r in sh.table.rows:
                    m = 1
                    for j, c in enumerate(r.cells):
                        cw = sh.table.columns[j].width / 914400
                        size = next((rr.font.size.pt for p in c.text_frame.paragraphs for rr in p.runs if rr.font.size), 12)
                        m = max(m, math.ceil(len(c.text) / max(1, int((cw - 0.15) * 72 / (size * 0.5)))))
                    est += m * size * 1.25 / 72 + 0.1
                if top + est > 6.85:
                    print(f"slide {i:>2} table {rows} rows: bottom ≈ {top + est:.1f} in (limit 6.85)  OVER")


if __name__ == "__main__":
    main(sys.argv[1])
