"""OCR tools: turn a scanned PDF or a photo into a searchable PDF the table agents can read.

Each page is rendered (or the image is taken as is), OCR'd, and written to a new PDF
that keeps the page image and adds an invisible text layer: every recognised word is
placed at its box, horizontally scaled to the box width, so pdfplumber/PyMuPDF see
words exactly where they are printed. Table ruling in the image is then found by
`raster_rules`, so the normal grid pipeline works unchanged.

Engines: macOS Vision (ocrmac) for Latin script and digits. Vision has no Hindi, so
when a page looks Devanagari-heavy and EasyOCR is installed, EasyOCR ('hi' + 'en')
is used for that page instead.
"""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pymupdf

from agri.config import ROOT

CACHE_DIR = ROOT / "data" / "ocr_cache"
UNICODE_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
RENDER_DPI = 300


def _vision_boxes(img) -> list[dict]:
    """Word-level boxes from Apple Live Text (macOS 13+); falls back to Vision line boxes."""
    from ocrmac import ocrmac
    w, h = img.size
    out = []
    try:
        results = ocrmac.OCR(img, framework="livetext", unit="token").recognize()
    except Exception:  # noqa: BLE001 - older macOS without Live Text
        results = ocrmac.OCR(img, recognition_level="accurate").recognize()
    for text, conf, (x, y, bw, bh) in results:
        out.append({"text": text, "conf": float(conf), "x0": x * w, "x1": (x + bw) * w,
                    "y0": (1 - y - bh) * h, "y1": (1 - y) * h})
    return out


def _easyocr_boxes(img) -> list[dict] | None:
    """None when EasyOCR is not installed or its models cannot be loaded (never breaks the pipeline)."""
    try:
        import easyocr  # noqa: F401  optional dependency for Hindi
        import numpy as np
        reader = _easyocr_reader()
    except Exception:  # noqa: BLE001 - missing package, model download failure, ...
        return None
    out = []
    for pts, text, conf in reader.readtext(np.array(img.convert("RGB"))):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out.append({"text": text, "conf": float(conf), "x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys)})
    return out


_READER = None


def _easyocr_reader():
    global _READER
    if _READER is None:
        import os

        import certifi
        # python.org builds of Python on macOS ship without root certificates; the first run
        # downloads EasyOCR's models over HTTPS, so point SSL at certifi's bundle
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        import easyocr
        _READER = easyocr.Reader(["hi", "en"], gpu=False, verbose=False)
    return _READER


def _looks_devanagari_heavy(boxes: list[dict]) -> bool:
    """Vision has no Hindi: it drops Devanagari words or turns them into non-English prefixes
    ('guIRt Arecanut'). So a page of numbers with almost no word labels, or with many words that
    are not English, probably carries Hindi."""
    if len(boxes) < 20:
        return False
    worded = [b for b in boxes if sum(ch.isalpha() for ch in b["text"]) >= 3]
    # thresholds measured on test pages: English tables 4-7% word boxes, a Hindi-labelled table 0.8%
    if len(worded) < 0.02 * len(boxes):
        return True                        # numbers but no word labels: labels in a script Vision cannot read
    from agri.tools.krutidev import _in_vocab, _vocabulary
    vocab = _vocabulary()

    def is_word(t: str) -> bool:
        t = t.strip(".,:;()[]|-'\"").lower()
        return len(t) >= 3 and t.isalpha() and t.isascii() and _in_vocab(t, vocab)
    # Vision reads a bilingual label "धान Paddy" as "<junk> Paddy": a non-word token before English words
    prefixed = 0
    for b in worded:
        toks = b["text"].split()
        if len(toks) >= 2 and not is_word(toks[0]) and any(is_word(t) for t in toks[1:]) \
                and not toks[0].replace(".", "").isdigit():
            prefixed += 1
    # English pages showed at most 4 such boxes; the bilingual DES scan showed 34 of 55
    if prefixed >= max(8, 0.3 * len(worded)):
        return True
    # word-level engines (Live Text) return the junk as separate tokens: share of unknown words.
    # Measured: English pages 3.6-11.5%, a bilingual Hindi DES page 17.5%.
    toks = [t.strip(".,:;()[]|-'\"") for b in worded for t in b["text"].split()]
    toks = [t for t in toks if len(t) >= 3 and any(ch.isalpha() for ch in t)]
    unknown = [t for t in toks if not t.isascii() or (t.isalpha() and not is_word(t))]
    return len(unknown) >= 10 and len(unknown) >= 0.15 * len(toks)


def _long_run_mask(dark, min_len: int):
    """Pixels that belong to a horizontal run of dark pixels at least min_len long (per row)."""
    import numpy as np
    h, w = dark.shape
    padded = np.zeros((h, w + 2), dtype=np.int8)
    padded[:, 1:-1] = dark
    diff = np.diff(padded, axis=1)
    mask = np.zeros_like(dark, dtype=bool)
    for r in np.where(dark.any(axis=1))[0]:
        starts = np.where(diff[r] == 1)[0]
        ends = np.where(diff[r] == -1)[0]
        for s0, e0 in zip(starts, ends):
            if e0 - s0 >= min_len:
                mask[r, s0:e0] = True
    return mask


def erase_rules(img):
    """Paint table ruling lines white, pixel-precisely. OCR engines skip digits that touch a rule
    ('2100.3|'); erasing whole columns instead would cut header words that a rule passes behind,
    so only pixels that are part of a long unbroken line segment are removed."""
    import numpy as np
    from PIL import Image
    arr = np.array(img.convert("L"))
    dark = arr < 160
    h, w = dark.shape
    horiz = _long_run_mask(dark, max(60, int(0.05 * w)))
    vert = _long_run_mask(dark.T, max(60, int(0.05 * h))).T
    lines = horiz | vert
    # thicken by one pixel to remove anti-aliased edges
    lines[1:, :] |= lines[:-1, :]
    lines[:, 1:] |= lines[:, :-1]
    out = arr.copy()
    out[lines] = 255
    return Image.fromarray(out)


def ocr_image(img, force_hindi: bool = False) -> tuple[list[dict], str]:
    clean = erase_rules(img)
    boxes = _vision_boxes(clean)
    if force_hindi or _looks_devanagari_heavy(boxes):
        alt = _easyocr_boxes(clean)
        if alt:
            # hybrid: Vision is the stronger digit reader, EasyOCR the only Hindi reader here
            numeric = [b for b in boxes if b["conf"] >= 0.5 and _NUMERIC.fullmatch(b["text"].replace(" ", ""))]
            words = [b for b in alt if not _NUMERIC.fullmatch(b["text"].replace(" ", ""))
                     and not any(_overlap(b, n) > 0.5 for n in numeric)]
            return numeric + words, "vision(digits)+easyocr(hi)"
        return boxes, "vision(en; Hindi engine not installed)"
    return boxes, "vision"


_NUMERIC = re.compile(r"[-−]?[\d.,]+")


def _overlap(a: dict, b: dict) -> float:
    ix = max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
    iy = max(0.0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
    area = max(1e-6, (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]))
    return ix * iy / area


def split_words(box: dict) -> list[dict]:
    """OCR often returns neighbouring cells as one box ('Total 2105.8'). Split it into words,
    sharing the box width by character count, so each word lands in its own table cell."""
    words = box["text"].split()
    if len(words) <= 1:
        return [{**box, "text": " ".join(words)}]
    total = sum(len(w) for w in words) + (len(words) - 1)
    unit = (box["x1"] - box["x0"]) / total
    out, x = [], box["x0"]
    for w in words:
        out.append({**box, "text": w, "x0": x, "x1": x + len(w) * unit})
        x += (len(w) + 1) * unit
    return out


def _page_images(src: Path):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    if src.suffix.lower() == ".pdf":
        with pymupdf.open(src) as d:
            for p in d:
                pix = p.get_pixmap(dpi=RENDER_DPI)
                yield Image.open(io.BytesIO(pix.tobytes("png"))), (p.rect.width, p.rect.height)
    else:
        img = Image.open(src)
        img.load()
        # treat the image as printed at RENDER_DPI so PDF coordinates stay realistic
        page_size = (img.width * 72 / RENDER_DPI, img.height * 72 / RENDER_DPI)
        if img.width < 3000:
            # photos and screenshots are often low resolution: OCR misses small digits, so upscale
            f = 3000 / img.width
            img = img.convert("RGB").resize((int(img.width * f), int(img.height * f)), Image.LANCZOS)
        yield img, page_size


def make_searchable_pdf(src: str | Path, force_hindi: bool = False) -> dict:
    """OCR every page of `src` (PDF or image) into a cached searchable PDF. Returns stats and the output path."""
    src = Path(src)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    out = CACHE_DIR / f"{digest}{'_hi' if force_hindi else ''}.pdf"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    font = pymupdf.Font(fontfile=UNICODE_FONT)
    doc = pymupdf.open()
    stats = {"pages": 0, "words": 0, "mean_conf": 0.0, "engines": []}
    confs = []
    for img, (pw, ph) in _page_images(src):
        page = doc.new_page(width=pw, height=ph)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        page.insert_image(page.rect, stream=buf.getvalue())
        boxes, engine = ocr_image(img, force_hindi=force_hindi)
        sx, sy = pw / img.width, ph / img.height
        page.insert_font(fontname="uni", fontfile=UNICODE_FONT)
        for b in (piece for box in boxes for piece in split_words(box)):
            text = b["text"]
            if not text:
                continue
            x0, y0, x1, y1 = b["x0"] * sx, b["y0"] * sy, b["x1"] * sx, b["y1"] * sy
            size = max(4.0, (y1 - y0) * 0.8)
            natural = font.text_length(text, fontsize=size) or 1.0
            # centre the word in its box; shrink only if it would overflow (OCR boxes are often padded,
            # and stretching a word to a padded box pushes its last letters into the next table cell)
            scale = min(1.0, (x1 - x0) / natural)
            origin = pymupdf.Point(x0 + ((x1 - x0) - natural * scale) / 2, y1 - (y1 - y0) * 0.2)
            page.insert_text(origin, text, fontsize=size, fontname="uni", render_mode=3,
                             morph=(origin, pymupdf.Matrix(scale, 1)))
            confs.append(b["conf"])
        stats["pages"] += 1
        stats["words"] += len(boxes)
        stats["engines"].append(engine)
    doc.save(out, garbage=3, deflate=True)
    stats["mean_conf"] = round(sum(confs) / len(confs), 3) if confs else 0.0
    stats["engines"] = sorted(set(stats["engines"]))
    stats["path"] = str(out)
    return stats


def quick_ocr_text(src: str | Path, max_pages: int = 1) -> str:
    """OCR text of the first page(s), used by the router to tell a scanned table from a map."""
    words = []
    for i, (img, _) in enumerate(_page_images(Path(src))):
        if i >= max_pages:
            break
        boxes, _ = ocr_image(img)
        words += [b["text"] for b in boxes]
    return " ".join(words)
