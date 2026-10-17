"""Build data/manifest.csv: provenance, checksum, language, modality and licence for every corpus file."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from agri.config import CORPUS_DIR, MANIFEST_PATH  # noqa: E402
from agri.sources import DOCUMENT_URLS, DOCUMENTS, SOURCES  # noqa: E402
from agri.tools.lang import detect_languages  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_profile(path: Path) -> dict:
    doc = pymupdf.open(path)
    texts = [p.get_text() for p in doc]
    low_text = sum(1 for t in texts if len(t.strip()) < 50)
    langs = detect_languages("\n".join(texts))
    modality = "pdf_digital" if low_text == 0 else ("pdf_scanned" if low_text == len(texts) else "pdf_mixed")
    return {"pages": len(texts), "modality": modality, **langs}


def main() -> None:
    rows = []
    for doc_id, rel, src, group, period, geo, notes in DOCUMENTS:
        path = CORPUS_DIR / rel
        stat = path.stat()
        info = {"pages": 1, "modality": "image", "languages": "en", "scripts": "Latin", "legacy_font": False}
        if path.suffix.lower() == ".pdf":
            info = pdf_profile(path)
        rows.append({
            "doc_id": doc_id,
            "file_name": path.name,
            "relative_path": rel,
            "source_id": src,
            "source_name": SOURCES[src]["name"],
            "portal_url": SOURCES[src]["portal_url"],
            "document_url": DOCUMENT_URLS[doc_id],
            "source_group": group,
            "period": period,
            "geography": geo,
            "modality": info["modality"],
            "pages": info["pages"],
            "languages": info["languages"],
            "scripts": info["scripts"],
            "legacy_font_encoding": info["legacy_font"],
            "size_bytes": stat.st_size,
            "sha256": sha256(path),
            # File timestamp is a proxy; replace with the real collection date from Phase 1 if it differs.
            "collection_date": dt.date.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime)).isoformat(),
            "license": SOURCES[src]["license"],
            "notes": notes,
        })
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {MANIFEST_PATH}")
    for r in rows:
        print(f"{r['doc_id']} {r['modality']:<12} {r['languages']:<8} legacy={r['legacy_font_encoding']!s:<5} {r['file_name']}")


if __name__ == "__main__":
    main()
