"""Design kit for the Phase 3 deck (python-pptx): palette, text that is measured and fitted before it is placed,
rounded cards, stat tiles, pills, arrows and native charts. All sizes in inches."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFont
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

# ---------------------------------------------------------------- palette (Andaman: sea, palm, paddy)
SEA = "0B3D4F"      # dominant dark
TEAL = "137C8B"
PALM = "2E7D4F"
PADDY = "D99A0B"    # accent
CORAL = "C8414F"
TINT = "EAF3F4"     # card tint
TINT2 = "F3F7F2"
INK = "1E2A30"
MUTED = "5B6B73"
WHITE = "FFFFFF"
LINE = "C9D6DA"
MEMBER = {"Suyash Tripathi": TEAL, "Abhineet Sharan": PADDY, "Shikhar Singhania": PALM}

HEAD, BODY = "Georgia", "Arial"
_FONTS = {("Georgia", False): "Georgia.ttf", ("Georgia", True): "Georgia Bold.ttf",
          ("Arial", False): "Arial.ttf", ("Arial", True): "Arial Bold.ttf"}
_FDIR = Path("/System/Library/Fonts/Supplemental")
W, H = 13.333, 7.5
NOTES: list[str] = []


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


# ---------------------------------------------------------------- text measurement
def _font(face: str, bold: bool, size: float):
    return ImageFont.truetype(str(_FDIR / _FONTS[(face, bold)]), max(1, int(round(size * 10))))


def wrap(text: str, face: str, bold: bool, size: float, width_in: float) -> list[str]:
    """Greedy word wrap using real font metrics (size in pt, width in inches)."""
    f = _font(face, bold, size)
    maxw = width_in * 72 * 10
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w_ in para.split(" "):
            t = (cur + " " + w_).strip()
            if f.getlength(t) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w_
        lines.append(cur)
    return lines


def text_height(paras: list[tuple[str, bool]], face: str, size: float, width_in: float, spacing: float = 1.18,
                para_gap: float = 0.35) -> float:
    n = 0.0
    for t, b in paras:
        n += len(wrap(t, face, b, size, width_in)) * spacing + para_gap
    return (n - para_gap) * size / 72


def fit_size(paras, face, width_in, height_in, smax, smin, spacing=1.18, para_gap=0.35) -> float:
    s = smax
    while s > smin and text_height(paras, face, s, width_in, spacing, para_gap) > height_in:
        s -= 0.5
    return s


# ---------------------------------------------------------------- primitives
class Slide:
    def __init__(self, prs, bg: str = WHITE):
        self.s = prs.slides.add_slide(prs.slide_layouts[6])
        self.idx = len(prs.slides)
        f = self.s.background.fill
        f.solid()
        f.fore_color.rgb = rgb(bg)
        self.dark = bg != WHITE

    # ---- text
    def text(self, x, y, w, h, paras, size=16, color=INK, face=BODY, bold=False, align="l", anchor="t",
             smin=12, fit=True, spacing=1.18, para_gap=0.35, italic=False, name=None):
        """paras: str | list[str | (text, bold) | (text, bold, color)]. Inline **bold** supported per paragraph."""
        if isinstance(paras, str):
            paras = [paras]
        norm = []
        for p in paras:
            if isinstance(p, str):
                norm.append((p, bold, color))
            elif len(p) == 2:
                norm.append((p[0], p[1], color))
            else:
                norm.append(p)
        pad = 0.06
        if fit:
            size = fit_size([(t.replace("**", ""), b) for t, b, _ in norm], face, w - 2 * pad, h - 2 * pad, size, smin,
                            spacing, para_gap)
        tb = self.s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        if name:
            tb.name = name
        tf = tb.text_frame
        tf.word_wrap = True
        for side in ("left", "right", "top", "bottom"):
            setattr(tf, f"margin_{side}", Inches(pad))
        tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
        for i, (t, b, col) in enumerate(norm):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
            p.line_spacing = spacing
            if i:
                p.space_before = Pt(size * para_gap)
            parts = t.split("**")
            for k, part in enumerate(parts):
                if not part:
                    continue
                r = p.add_run()
                r.text = part
                r.font.size = Pt(size)
                r.font.name = face
                r.font.bold = b or (k % 2 == 1)
                r.font.italic = italic
                r.font.color.rgb = rgb(col)
        return tb

    def bullets(self, x, y, w, h, items, size=16, color=INK, smin=12, dot=PADDY, gap=0.45):
        """Bulleted list as separate aligned rows: coloured dot + text (inline **bold**)."""
        s = fit_size([(i.replace("**", ""), False) for i in items], BODY, w - 0.35, h, size, smin, 1.15, gap)
        yy = y
        for it in items:
            hh = text_height([(it.replace("**", ""), False)], BODY, s, w - 0.35, 1.15, 0) + 0.04
            self.circle(x + 0.02, yy + s / 72 * 0.38, 0.11, dot)
            self.text(x + 0.25, yy - 0.06, w - 0.25, hh + 0.12, [it], size=s, color=color, fit=False, spacing=1.15)
            yy += hh + s / 72 * gap
        return yy

    def title(self, t, sub=None, color=None):
        col = color or (WHITE if self.dark else SEA)
        self.text(0.6, 0.38, 12.1, 1.0, [t], size=30, color=col, face=HEAD, bold=True, smin=24, anchor="m", spacing=1.05)
        if sub:
            self.text(0.62, 1.32, 12.0, 0.4, [sub], size=14, color=MUTED if not self.dark else "B8D3D9", smin=12)

    # ---- shapes
    def rect(self, x, y, w, h, fill=TINT, line=None, radius=0.08, shadow=False, name=None):
        shp = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                      Inches(x), Inches(y), Inches(w), Inches(h))
        if radius:
            shp.adjustments[0] = min(0.5, radius / min(w, h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
        if line:
            shp.line.color.rgb = rgb(line)
            shp.line.width = Pt(1)
        else:
            shp.line.fill.background()
        if not shadow:
            sp = shp._element.spPr
            ef = sp.find(qn("a:effectLst"))
            if ef is None:
                sp.append(sp.makeelement(qn("a:effectLst"), {}))
        if name:
            shp.name = name
        shp.text_frame.text = ""
        return shp

    def circle(self, x, y, d, fill, text=None, size=14, color=WHITE, bold=True):
        c = self.s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
        c.fill.solid()
        c.fill.fore_color.rgb = rgb(fill)
        c.line.fill.background()
        sp = c._element.spPr
        sp.append(sp.makeelement(qn("a:effectLst"), {}))
        tf = c.text_frame
        for side in ("left", "right", "top", "bottom"):
            setattr(tf, f"margin_{side}", 0)
        if text:
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = text
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.name = BODY
            r.font.color.rgb = rgb(color)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        return c

    def pill(self, x, y, text, fill=TEAL, color=WHITE, size=12, h=0.34, padx=0.18, bold=True):
        f = _font(BODY, bold, size)
        w = f.getlength(text) / 720 + 2 * padx
        self.rect(x, y, w, h, fill, radius=h / 2)
        self.text(x, y, w, h, [text], size=size, color=color, bold=bold, align="c", anchor="m", fit=False)
        return w

    def arrow(self, x1, y1, x2, y2, color=MUTED, width=2.0):
        c = self.s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        c.line.color.rgb = rgb(color)
        c.line.width = Pt(width)
        ln = c.line._get_or_add_ln()
        tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
        ln.append(tail)
        return c

    def stat(self, x, y, w, h, value, label, color=SEA, fill=TINT, vsize=40, lsize=13):
        self.rect(x, y, w, h, fill)
        self.text(x + 0.12, y + 0.1, w - 0.24, h * 0.58, [value], size=vsize, color=color, face=HEAD, bold=True,
                  align="l", anchor="b", smin=20)
        self.text(x + 0.12, y + h * 0.62, w - 0.24, h * 0.36, [label], size=lsize, color=MUTED, smin=10)

    def image(self, path, x, y, w=None, h=None, fit_box=None):
        """Place an image; with fit_box=(x,y,w,h) it is scaled to fit and centred."""
        if fit_box:
            bx, by, bw, bh = fit_box
            iw, ih = Image.open(path).size
            sc = min(bw / iw, bh / ih)
            w, h = iw * sc, ih * sc
            x, y = bx + (bw - w) / 2, by + (bh - h) / 2
        return self.s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)

    def movie(self, mp4, poster, box):
        bx, by, bw, bh = box
        iw, ih = Image.open(poster).size
        sc = min(bw / iw, bh / ih)
        w, h = iw * sc, ih * sc
        return self.s.shapes.add_movie(str(mp4), Inches(bx + (bw - w) / 2), Inches(by + (bh - h) / 2), Inches(w), Inches(h),
                                       poster_frame_image=str(poster), mime_type="video/mp4")

    def footer(self, n, presenter=None):
        col = "8FB3BC" if self.dark else MUTED
        self.text(11.4, 7.02, 1.5, 0.32, [f"{n}"], size=11, color=col, align="r", fit=False)
        self.text(0.6, 7.02, 6.0, 0.32, ["Team 34 · Andaman & Nicobar Islands · CS F/U 407"], size=10, color=col, fit=False)
        if presenter:
            c = MEMBER.get(presenter, TEAL)
            self.circle(7.95, 7.04, 0.26, c)
            self.text(8.27, 7.0, 3.1, 0.34, [f"{presenter}"], size=11, color=col, fit=False, anchor="m")

    def notes(self, text):
        """Speaker notes are collected, not embedded: Keynote cannot import python-pptx's generated notes master.
        They are written to docs/speaker_notes.md by the deck builder."""
        NOTES.append((self.idx, text))

    # ---- tables
    def table(self, x, y, w, rows, col_w, header_fill=SEA, size=12, row_h=0.36, zebra=True, bold_col0=False,
              highlight_last=False):
        t = self.s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows))).table
        for j, cw in enumerate(col_w):
            t.columns[j].width = Inches(cw)
        tblPr = t._tbl.tblPr
        for k in ("bandRow", "firstRow"):
            tblPr.set(k, "0")
        st = tblPr.find(qn("a:tableStyleId"))
        if st is not None:
            tblPr.remove(st)
        for i, r in enumerate(rows):
            t.rows[i].height = Inches(row_h)
            for j, v in enumerate(r):
                c = t.cell(i, j)
                c.margin_left = c.margin_right = Inches(0.08)
                c.margin_top = c.margin_bottom = Inches(0.03)
                c.vertical_anchor = MSO_ANCHOR.MIDDLE
                fill = header_fill if i == 0 else (TINT if (zebra and i % 2 == 0) else WHITE)
                if highlight_last and i == len(rows) - 1:
                    fill = "FCEFD2"
                c.fill.solid()
                c.fill.fore_color.rgb = rgb(fill)
                tf = c.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                txt = "" if v is None else str(v)
                col = WHITE if i == 0 else INK
                if txt in ("✓", "✗", "~"):
                    col = {"✓": PALM, "✗": CORAL, "~": PADDY}[txt]
                rr = p.add_run()
                rr.text = txt
                rr.font.size = Pt(size)
                rr.font.name = BODY
                rr.font.bold = i == 0 or (bold_col0 and j == 0) or txt in ("✓", "✗") or (highlight_last and i == len(rows) - 1)
                rr.font.color.rgb = rgb(col)
        return t

    # ---- charts
    def bar_chart(self, x, y, w, h, cats, series: dict, colors, number_format='0.00', vmax=1.0, horizontal=False,
                  legend=True, label_size=12, cat_size=12):
        cd = CategoryChartData()
        cd.categories = cats
        for name, vals in series.items():
            cd.add_series(name, vals)
        kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
        gf = self.s.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd)
        ch = gf.chart
        ch.font.name = BODY
        ch.font.size = Pt(cat_size)
        ch.font.color.rgb = rgb(INK)
        ch.has_legend = legend and len(series) > 1
        if ch.has_legend:
            ch.legend.position = XL_LEGEND_POSITION.TOP
            ch.legend.include_in_layout = False
            ch.legend.font.size = Pt(cat_size)
        va = ch.value_axis
        va.maximum_scale = vmax
        va.minimum_scale = 0
        va.has_major_gridlines = True
        va.major_unit = 0.2 if vmax <= 1.5 else None
        va.major_gridlines.format.line.color.rgb = rgb("E3EAEC")
        va.format.line.fill.background()
        va.tick_labels.font.size = Pt(cat_size - 1)
        va.tick_labels.font.color.rgb = rgb(MUTED)
        va.tick_labels.number_format = '0.0' if vmax <= 1.5 else '0'
        va.tick_labels.number_format_is_linked = False
        ca = ch.category_axis
        ca.format.line.color.rgb = rgb(LINE)
        ca.tick_labels.font.size = Pt(cat_size)
        ca.has_major_gridlines = False
        plot = ch.plots[0]
        plot.gap_width = 60
        plot.overlap = -10 if len(series) > 1 else 0
        for k, s in enumerate(plot.series):
            s.format.fill.solid()
            s.format.fill.fore_color.rgb = rgb(colors[k % len(colors)])
            s.format.line.fill.background()
            dl = s.data_labels
            dl.show_value = True
            dl.number_format = number_format
            dl.number_format_is_linked = False
            dl.font.size = Pt(label_size)
            dl.font.bold = True
            dl.font.color.rgb = rgb(INK)
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        return ch


def new_prs():
    from pptx import Presentation
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    return prs


_ = (Emu,)
