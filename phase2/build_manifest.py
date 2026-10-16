from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from pypdf import PdfReader
from source_paths import phase1_corpus_root

ROOT = Path(__file__).resolve().parents[1]
CORPUS = phase1_corpus_root()
OUT = Path(__file__).resolve().parent / "data" / "manifest.csv"

GROUPS = {
    "basic stats": "G2_BASIC_STATS",
    "island wise stats": "G3_ISLAND_PROFILES",
    "misc data": "G4_NARRATIVE",
    "price analysis": "G5_PRICES",
    "sat bhuvan data(lulc)": "G7_LULC",
    "total area and prod": "G1_AREA_PRODUCTION",
}


def source_for(rel: Path) -> tuple[str, str, str]:
    folder = rel.parts[0].lower()
    name = rel.name.lower()
    if "total area" in folder:
        return "Department of Agriculture, A&N Administration", "government statistics", "English"
    if "basic stats" in folder or "island wise" in folder or "price analysis" in folder:
        lang = "Hindi + English (Kruti Dev)" if "basic statistics" in name or "islandwise" in name else "English"
        return "Directorate of Economics & Statistics, A&N Administration", "government statistics", lang
    if "misc data" in folder:
        if "food processing" in name:
            return "Ministry of Food Processing Industries", "government report", "English"
        return "Directorate of Economics & Statistics, A&N Administration", "government statistics", "English"
    if "bhuvan" in folder:
        return "Bhuvan / NRSC / ISRO", "geospatial publication", "English"
    return "NRSC / ISRO", "geospatial publication", "English"


def modality(path: Path) -> tuple[str, int | str]:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return "image", ""
    try:
        return "PDF", len(PdfReader(str(path)).pages)
    except Exception:
        return "PDF (page count unavailable)", ""


def main() -> None:
    files = sorted(p for p in CORPUS.rglob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"})
    fields = ["doc_id", "file_name", "relative_path", "source_group", "source_name", "source_type", "source_url",
              "language", "modality", "pages", "sha256", "license_note", "implementation_status"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, path in enumerate(files, 1):
            rel = path.relative_to(CORPUS)
            group = GROUPS[rel.parts[0].lower()]
            source, source_type, language = source_for(rel)
            mod, pages = modality(path)
            name_lower = path.name.lower()
            if "census" in name_lower and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                group = "G6_CENSUS_IMAGE"
            elif "map" in name_lower and path.suffix.lower() in {".jpg", ".jpeg", ".png"} or "map of india" in name_lower:
                group = "G8_RASTER_MAPS"
            if group == "G7_LULC" and "atlas" in name_lower:
                status = "pending: chart digitisation"
            elif group == "G8_RASTER_MAPS":
                status = "out of scope: raster map"
            elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                status = "pending: OCR reader"
            else:
                status = "implemented"
            writer.writerow({"doc_id": f"P1-{i:02d}", "file_name": path.name, "relative_path": rel.as_posix(),
                             "source_group": group, "source_name": source, "source_type": source_type,
                             "source_url": "not supplied in uploaded Phase 1 materials", "language": language,
                             "modality": mod, "pages": pages,
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "license_note": "See original Phase 1 source/document; terms not independently verified",
                             "implementation_status": status})
    print(f"Wrote {len(files)} Phase 1 source entries to {OUT}")


if __name__ == "__main__":
    main()
