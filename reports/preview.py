"""Rough PNG preview of a .pptx slide (layout check when Keynote/PowerPoint are not scriptable)."""
import io
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def render(path, idx, out, dpi=40):
    prs = Presentation(path)
    W, H = int(prs.slide_width / 914400 * dpi), int(prs.slide_height / 914400 * dpi)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    s = prs.slides[idx]
    for sh in s.shapes:
        x, y = int(sh.left / 914400 * dpi), int(sh.top / 914400 * dpi)
        w, h = int(sh.width / 914400 * dpi), int(sh.height / 914400 * dpi)
        if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
            try:
                im = Image.open(io.BytesIO(sh.image.blob)).convert("RGB").resize((max(1, w), max(1, h)))
                img.paste(im, (x, y))
            except Exception:
                d.rectangle([x, y, x + w, y + h], outline="purple")
            continue
        if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            try:
                c = sh.fill.fore_color.rgb if sh.fill.type == 1 else None
                d.rectangle([x, y, x + w, y + h], fill=f"#{c}" if c else None, outline="#BBBBBB")
            except Exception:
                d.rectangle([x, y, x + w, y + h], outline="#BBBBBB")
        if sh.has_text_frame and sh.text_frame.text.strip():
            ty = y
            for p in sh.text_frame.paragraphs:
                size = next((r.font.size.pt for r in p.runs if r.font.size), 18)
                px = max(6, int(size / 72 * dpi))
                f = ImageFont.truetype(FONT, px)
                cpl = max(5, int(w / (px * 0.5)))
                for line in textwrap.wrap(p.text, cpl) or [""]:
                    d.text((x + 2, ty), line, fill="black", font=f)
                    ty += int(px * 1.2)
            if ty > y + h + 2:
                d.rectangle([x, y, x + w, ty], outline="red", width=2)
    img.save(out)
    print(out)


if __name__ == "__main__":
    render(sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 40)
