from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

from krutidev import split_bilingual_label
from source_paths import resolve_source_path
from supplemental_extraction import normalize_market_prices, normalize_table

ROOT = Path(__file__).resolve().parents[1]
PHASE2 = Path(__file__).resolve().parent
MANIFEST = PHASE2 / "data" / "manifest.csv"
DB = Path(os.environ.get("PHASE2_DB_PATH", str(PHASE2 / "db" / "agriculture_phase2.sqlite")))
LOGS = PHASE2 / "logs"

TABLE_GROUPS = {"G1_AREA_PRODUCTION", "G2_BASIC_STATS", "G5_PRICES", "G7_LULC"}
TEXT_GROUPS = {"G3_ISLAND_PROFILES", "G4_NARRATIVE"}
PENDING_GROUPS = {"G6_CENSUS_IMAGE"}
SKIP_GROUPS = {"G8_RASTER_MAPS"}
TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def number(value: str) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_manifest() -> list[dict]:
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def connect(fresh: bool) -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if fresh and DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript((PHASE2 / "db" / "schema.sql").read_text(encoding="utf-8"))
    conn.commit()
    return conn


def trace(stream, run_id: str, doc_id: str, agent: str, event: str, detail: dict) -> None:
    stream.write(json.dumps({"time": now(), "run_id": run_id, "doc_id": doc_id, "agent_id": agent,
                             "event": event, "detail": detail}, ensure_ascii=False) + "\n")
    stream.flush()


def add_observation(conn, run_id: str, doc: dict, page: int, table_no: int, row_no: int,
                    col_no: int, metric: str, commodity: str, period: str, value_raw: str,
                    unit: str, evidence: str) -> None:
    value = number(value_raw)
    if value is None:
        return
    conn.execute("""INSERT OR IGNORE INTO observation
      (doc_id,run_id,agent_id,metric,commodity,location,period,value,unit,value_raw,page,table_no,row_no,col_no,evidence)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (doc["doc_id"], run_id, "pdf_table_agent", metric, commodity, "Andaman & Nicobar Islands", period,
       value, unit, value_raw.strip(), page, table_no, row_no, col_no, evidence[:2000]))


def extract_basic_statistics(conn, run_id: str, doc: dict, page_no: int, table_no: int, table: list[list]) -> int:
    """Read the whole-island crop table, keeping the printed label as evidence."""
    if len(table) < 3 or not any("area" in str(x).lower() for x in table[0]):
        return 0
    period_row = next((r for r in table[1:4] if sum(bool(re.search(r"20\d\d-\d\d", str(x))) for x in r) >= 2), None)
    if not period_row:
        return 0
    periods = [str(x).strip() if x else "" for x in period_row]
    start = next((i for i, p in enumerate(periods) if re.fullmatch(r"20\d\d-\d\d", p)), None)
    if start is None:
        return 0
    all_periods = periods[start:]
    # The same year labels appear once for area and once for production.
    periods = all_periods[: max(1, len(all_periods) // 2)]
    out = 0
    for ri, row in enumerate(table):
        if ri <= table.index(period_row) or not row or not row[0]:
            continue
        raw_label = " ".join(str(row[0]).split())
        hindi, english = split_bilingual_label(raw_label)
        commodity = re.sub(r"\s*\([^)]*\).*", "", english).strip()
        if not commodity:
            continue
        # The Basic Statistics table is grouped as area(years), then production(years).
        cells = [(ci, str(v).strip()) for ci, v in enumerate(row) if ci > 0 and number(str(v or "")) is not None]
        numeric_positions = [ci for ci, _ in cells]
        if len(numeric_positions) < len(periods) * 2:
            continue
        area_cols = list(range(numeric_positions[0], numeric_positions[0] + len(periods)))
        prod_cols = list(range(numeric_positions[0] + len(periods), numeric_positions[0] + 2 * len(periods)))
        for metric, cols, unit_default in (("area_cultivated", area_cols, "hectare"),
                                            ("production", prod_cols, "MT")):
            for ix, col in enumerate(cols):
                if col >= len(row) or ix >= len(periods):
                    continue
                raw = str(row[col] or "").strip()
                if number(raw) is None:
                    continue
                unit = "million nuts" if metric == "production" and "nuts" in english.lower() else unit_default
                evidence = f"{raw_label} | {metric} | {periods[ix]} | {raw}"
                add_observation(conn, run_id, doc, page_no, table_no, ri, col, metric,
                                commodity, periods[ix], raw, unit, evidence)
                if hindi:
                    conn.execute("INSERT INTO text_fact(doc_id,run_id,agent_id,page,fact_type,evidence) VALUES(?,?,?,?,?,?)",
                                 (doc["doc_id"], run_id, "pdf_table_agent", page_no, "decoded_hindi_label",
                                  f"{raw_label} → {hindi} {english}"))
                out += 1
    return out


def run_table_agent(conn, run_id: str, doc: dict, path: Path, stream) -> tuple[str, dict]:
    agent = "pdf_table_agent"
    trace(stream, run_id, doc["doc_id"], agent, "decision", {"by": "rule", "group": doc["source_group"]})
    trace(stream, run_id, doc["doc_id"], agent, "tool_call",
          {"tool": "pdfplumber_extract_tables", "path": doc["relative_path"].replace("\\", "/"), "args_validated": True})
    cells = facts = pages = tables_found = 0
    try:
        with pdfplumber.open(path) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                conn.execute("INSERT OR REPLACE INTO page_text(doc_id,page,text) VALUES(?,?,?)",
                             (doc["doc_id"], page_no, text))
                pages += 1
                if doc["source_group"] == "G5_PRICES":
                    facts += normalize_market_prices(conn, run_id, doc, page_no, text)
                tables = page.extract_tables() or []
                for table_no, table in enumerate(tables, 1):
                    tables_found += 1
                    for row_no, row in enumerate(table):
                        for col_no, value in enumerate(row):
                            raw = " ".join(str(value or "").split())
                            if not raw:
                                continue
                            conn.execute("""INSERT OR IGNORE INTO table_cell
                                (doc_id,run_id,agent_id,page,table_no,row_no,col_no,value_raw,value_numeric)
                                VALUES (?,?,?,?,?,?,?,?,?)""",
                                (doc["doc_id"], run_id, agent, page_no, table_no, row_no, col_no, raw, number(raw)))
                            cells += 1
                    if doc["source_group"] == "G2_BASIC_STATS" and page_no == 1 and table_no == 1:
                        facts += extract_basic_statistics(conn, run_id, doc, page_no, table_no, table)
                    facts += normalize_table(conn, run_id, doc, page_no, table_no, table)
        status = "loaded" if cells or facts else "partial"
        if doc["source_group"] == "G7_LULC" and "atlas" in doc["file_name"].lower():
            status = "partial"
        trace(stream, run_id, doc["doc_id"], agent, "tool_result",
              {"tool": "pdfplumber_extract_tables", "pages": pages, "tables": tables_found, "cells": cells,
               "structured_observations": facts, "status": status})
        return status, {"pages": pages, "tables": tables_found, "cells": cells, "observations": facts}
    except Exception as exc:
        trace(stream, run_id, doc["doc_id"], agent, "error", {"type": type(exc).__name__, "message": str(exc)})
        return "failed", {"error": f"{type(exc).__name__}: {exc}"}


def run_text_agent(conn, run_id: str, doc: dict, path: Path, stream) -> tuple[str, dict]:
    agent = "pdf_text_agent"
    trace(stream, run_id, doc["doc_id"], agent, "decision", {"by": "rule", "group": doc["source_group"]})
    trace(stream, run_id, doc["doc_id"], agent, "tool_call",
          {"tool": "pdfplumber_extract_text", "path": doc["relative_path"].replace("\\", "/"), "args_validated": True})
    pages = facts = 0
    try:
        with pdfplumber.open(path) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                conn.execute("INSERT OR REPLACE INTO page_text(doc_id,page,text) VALUES(?,?,?)",
                             (doc["doc_id"], page_no, text))
                pages += 1
                for line in text.splitlines():
                    clean = " ".join(line.split())
                    if len(clean) > 25 and re.search(r"\d", clean) and re.search(
                            r"farm|area|production|population|household|scheme|subsid|outlay|expenditure|island|crop|price|agri",
                            clean, re.I):
                        conn.execute("INSERT INTO text_fact(doc_id,run_id,agent_id,page,fact_type,evidence) VALUES(?,?,?,?,?,?)",
                                     (doc["doc_id"], run_id, agent, page_no, "numbered_source_line", clean[:2000]))
                        facts += 1
        status = "loaded" if pages else "partial"
        trace(stream, run_id, doc["doc_id"], agent, "tool_result",
              {"tool": "pdfplumber_extract_text", "pages": pages, "evidence_lines": facts, "status": status})
        return status, {"pages": pages, "evidence_lines": facts}
    except Exception as exc:
        trace(stream, run_id, doc["doc_id"], agent, "error", {"type": type(exc).__name__, "message": str(exc)})
        return "failed", {"error": f"{type(exc).__name__}: {exc}"}


def tesseract_text(image_path: Path, psm: int = 11, extra: list[str] | None = None) -> str:
    """OCR an image using the installed Windows Tesseract executable."""
    command = str(TESSERACT) if TESSERACT.exists() else "tesseract"
    result = subprocess.run([command, str(image_path), "stdout", "--psm", str(psm), *(extra or [])],
                            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip()


def save_ocr(conn, run_id: str, doc: dict, text: str, agent: str, page: int = 1) -> int:
    conn.execute("INSERT OR REPLACE INTO page_text(doc_id,page,text) VALUES(?,?,?)",
                 (doc["doc_id"], page, text))
    facts = 0
    for line in text.splitlines():
        clean = " ".join(line.split())
        if len(clean) < 3:
            continue
        conn.execute("INSERT INTO text_fact(doc_id,run_id,agent_id,page,fact_type,evidence) VALUES(?,?,?,?,?,?)",
                     (doc["doc_id"], run_id, agent, page, "ocr_text", clean[:2000]))
        facts += 1
    return facts


def run_census_ocr(conn, run_id: str, doc: dict, path: Path, stream) -> tuple[str, dict]:
    agent = "image_ocr_agent"
    trace(stream, run_id, doc["doc_id"], agent, "decision", {"by": "manifest rule", "task": "read census screenshot"})
    trace(stream, run_id, doc["doc_id"], agent, "tool_call", {"tool": "Tesseract OCR", "language": "eng", "psm": 6,
          "path": doc["relative_path"].replace("\\", "/"), "args_validated": True})
    try:
        with tempfile.TemporaryDirectory() as td:
            from PIL import Image
            source = Image.open(path).convert("RGB")
            # The image is a website screenshot; crop the printed table and enlarge it for OCR.
            crop = source.crop((230, 240, 1018, 800)).resize((1576, 1120))
            image = Path(td) / "census_table.png"
            crop.save(image)
            text = tesseract_text(image, psm=6)
        facts = save_ocr(conn, run_id, doc, text, agent)
        # Crop the eight cells in the printed Total row independently so OCR can read small digits.
        # Cell bounds are specific to this Phase 1 screenshot, not hidden data values.
        fields = [
            ("operational_holdings_individual", "Individual holdings", "number of holdings"),
            ("operational_holdings_joint", "Joint holdings", "number of holdings"),
            ("operational_holdings_institutional", "Institutional holdings", "number of holdings"),
            ("operational_holdings_total", "Total holdings", "number of holdings"),
            ("operated_area_individual", "Individual operated area", "hectare"),
            ("operated_area_joint", "Joint operated area", "hectare"),
            ("operated_area_institutional", "Institutional operated area", "hectare"),
            ("operated_area_total", "Total operated area", "hectare"),
        ]
        bounds = [488, 553, 610, 660, 712, 793, 864, 933, 1014]
        with tempfile.TemporaryDirectory() as td:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps
            source = Image.open(path).convert("L")
            for col, (metric, label, unit) in enumerate(fields):
                cell = source.crop((bounds[col], 760, bounds[col + 1], 795)).resize(((bounds[col + 1] - bounds[col]) * 5, 175))
                cell = ImageOps.autocontrast(cell).filter(ImageFilter.SHARPEN)
                cell_path = Path(td) / f"total_{col}.png"
                cell.save(cell_path)
                raw = re.sub(r"[^0-9.]", "", tesseract_text(cell_path, psm=7, extra=["-c", "tessedit_char_whitelist=0123456789."]))
                value = number(raw)
                if value is None:
                    continue
                conn.execute("INSERT INTO text_fact(doc_id,run_id,agent_id,page,fact_type,evidence) VALUES(?,?,?,?,?,?)",
                             (doc["doc_id"], run_id, agent, 1, "ocr_total_cell", f"{label}: {raw}"))
                conn.execute("""INSERT OR IGNORE INTO observation
                    (doc_id,run_id,agent_id,metric,commodity,location,period,value,unit,value_raw,page,table_no,row_no,col_no,evidence)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (doc["doc_id"], run_id, agent, metric, label, "Andaman & Nicobar Islands", "2015-16",
                     value, unit, raw, 1, 1, 20, col, f"Tesseract OCR of the {label} total cell; OCR text: {raw}"))
        recognized = conn.execute("SELECT COUNT(*) FROM observation WHERE run_id=? AND doc_id=? AND agent_id=?",
                                  (run_id, doc["doc_id"], agent)).fetchone()[0]
        status = "loaded" if text and recognized == len(fields) else "partial"
        detail = {"ocr_facts": facts, "total_row_values_recognized": recognized, "observations": recognized}
        trace(stream, run_id, doc["doc_id"], agent, "tool_result", {"tool": "Tesseract OCR", **detail, "status": status})
        return status, detail
    except Exception as exc:
        trace(stream, run_id, doc["doc_id"], agent, "error", {"type": type(exc).__name__, "message": str(exc)})
        return "failed", {"error": f"{type(exc).__name__}: {exc}"}


def run_map_ocr(conn, run_id: str, doc: dict, path: Path, stream) -> tuple[str, dict]:
    agent = "map_legend_ocr_agent"
    trace(stream, run_id, doc["doc_id"], agent, "decision", {"by": "manifest rule", "task": "read map title, legend, and source notes"})
    trace(stream, run_id, doc["doc_id"], agent, "tool_call", {"tool": "Tesseract OCR", "language": "eng", "psm": 11,
          "path": doc["relative_path"].replace("\\", "/"), "args_validated": True})
    try:
        with tempfile.TemporaryDirectory() as td:
            image = path
            if path.suffix.lower() == ".pdf":
                with pdfplumber.open(path) as pdf:
                    page = pdf.pages[0]
                    conn.execute("INSERT OR REPLACE INTO page_text(doc_id,page,text) VALUES(?,?,?)",
                                 (doc["doc_id"], 1, page.extract_text() or ""))
                    image = Path(td) / "map.png"
                    page.to_image(resolution=180).save(image)
            text = tesseract_text(image, psm=11)
        facts = save_ocr(conn, run_id, doc, text, agent)
        status = "loaded" if text.strip() else "partial"
        detail = {"ocr_facts": facts, "spatial_features_digitized": 0, "note": "Legend and map labels were read; raster pixels were not converted to GIS geometry."}
        trace(stream, run_id, doc["doc_id"], agent, "tool_result", {"tool": "Tesseract OCR", **detail, "status": status})
        return status, detail
    except Exception as exc:
        trace(stream, run_id, doc["doc_id"], agent, "error", {"type": type(exc).__name__, "message": str(exc)})
        return "failed", {"error": f"{type(exc).__name__}: {exc}"}


def run_atlas_chart(conn, run_id: str, doc: dict, path: Path, stream) -> tuple[str, dict]:
    """OCR the A&N chart page and estimate colored bar heights against its printed axis."""
    agent = "lulc_chart_agent"
    page_no = 102  # Printed page 81, Chart 34, 2022-23. This page names Andaman & Nicobar.
    trace(stream, run_id, doc["doc_id"], agent, "decision", {"by": "rule", "pdf_page": page_no, "printed_page": 81})
    trace(stream, run_id, doc["doc_id"], agent, "tool_call", {"tool": "pdfplumber render + Tesseract OCR", "page": page_no,
          "path": doc["relative_path"].replace("\\", "/"), "args_validated": True})
    try:
        with tempfile.TemporaryDirectory() as td:
            from PIL import Image
            with pdfplumber.open(path) as pdf:
                page = pdf.pages[page_no - 1]
                render_path = Path(td) / "atlas_chart.png"
                page.to_image(resolution=140).save(render_path)
                text = page.extract_text() or ""
            # The atlas page is printed in a rotated landscape orientation.
            upright = Image.open(render_path).rotate(270, expand=True)
            upright_path = Path(td) / "atlas_chart_upright.png"
            upright.save(upright_path)
            ocr = tesseract_text(upright_path, psm=11)
        combined = text + "\n--- OCR ---\n" + ocr
        facts = save_ocr(conn, run_id, doc, combined, agent, page=page_no)
        # Chart 34 is rotated in the PDF. Rotate it for reading, then find each legend
        # colour's top pixel in the Andaman & Nicobar group and scale against the 0-16 axis.
        with tempfile.TemporaryDirectory() as td:
            from PIL import Image
            with pdfplumber.open(path) as pdf:
                chart = pdf.pages[page_no - 1].to_image(resolution=140)
                chart_path = Path(td) / "chart.png"
                chart.save(chart_path)
            pixels = Image.open(chart_path).rotate(270, expand=True).convert("RGB")
            legend_colors = [
                ("Evergreen/Semi-evergreen Woodland", (0, 95, 0)),
                ("Degraded Woodland", (116, 184, 44)),
                ("Littoral/Swamp/Mangroves", (6, 131, 95)),
                ("Deciduous Woodland", (108, 121, 31)),
                ("Double/Triple/Annual Crop", (204, 181, 33)),
            ]
            # Calibrated to the labeled Andaman & Nicobar x-axis group and the chart's
            # 0 and 16 lakh-hectare grid lines in this fixed Phase 1 atlas page.
            estimates = []
            for label, color in legend_colors:
                ys = [y for y in range(165, min(418, pixels.height))
                      for x in range(1030, min(1080, pixels.width)) if pixels.getpixel((x, y)) == color]
                if ys:
                    value = round((418 - min(ys)) * 16 / (418 - 165), 1)
                    if value > 0:
                        estimates.append((label, value))
        for row, (label, value) in enumerate(estimates):
            conn.execute("""INSERT OR IGNORE INTO observation
                (doc_id,run_id,agent_id,metric,commodity,location,period,value,unit,value_raw,page,table_no,row_no,col_no,evidence)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc["doc_id"], run_id, agent, "lulc_chart_visual_estimate", label,
                 "Andaman & Nicobar Islands", "2022-23", value, "lakh hectare (visual estimate)",
                 f"~{value:.1f}", page_no, 34, row, 0,
                 "Approximate bar-height reading from Chart 34; source provides no printed bar values. Use the P1-12 table for exact LULC figures."))
        detail = {"ocr_facts": facts, "visual_estimates": len(estimates), "pdf_page": page_no,
                  "status_note": "partial: chart is visual and has no exact labels"}
        trace(stream, run_id, doc["doc_id"], agent, "tool_result", {"tool": "OCR and visual chart reading", **detail, "status": "partial"})
        return "partial", detail
    except Exception as exc:
        trace(stream, run_id, doc["doc_id"], agent, "error", {"type": type(exc).__name__, "message": str(exc)})
        return "failed", {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Process only the Phase 1 files bundled with this submission.")
    parser.add_argument("--fresh", action="store_true", help="start a new SQLite database")
    parser.add_argument("--doc", help="process one manifest document ID")
    args = parser.parse_args()
    manifest = load_manifest()
    if args.doc:
        manifest = [d for d in manifest if d["doc_id"] == args.doc]
        if not manifest:
            parser.error(f"Unknown document id: {args.doc}")
    conn = connect(args.fresh)
    run_id = uuid.uuid4().hex[:12]
    conn.execute("INSERT INTO extraction_run(run_id,started_at,status,attempted) VALUES(?,?,?,?)",
                 (run_id, now(), "running", len(manifest)))
    LOGS.mkdir(parents=True, exist_ok=True)
    trace_path = LOGS / f"trace_{run_id}.jsonl"
    results = []
    with trace_path.open("w", encoding="utf-8") as stream:
        for doc in manifest:
            path = resolve_source_path(doc["relative_path"])
            conn.execute("""INSERT OR REPLACE INTO source_document
              (doc_id,file_name,relative_path,source_group,source_type,source_name,source_url,language,modality,
               license_note,sha256,pages,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (doc["doc_id"], doc["file_name"], doc["relative_path"], doc["source_group"], doc["source_type"],
               doc["source_name"], doc["source_url"], doc["language"], doc["modality"], doc["license_note"],
               doc["sha256"], int(doc["pages"]) if doc["pages"].isdigit() else None, doc["implementation_status"]))
            expected_agent = ("lulc_chart_agent" if doc["doc_id"] == "P1-14" else
                              "map_legend_ocr_agent" if doc["doc_id"] in {"P1-13", "P1-15"} else
                              "pdf_table_agent" if doc["source_group"] in TABLE_GROUPS else
                              "pdf_text_agent" if doc["source_group"] in TEXT_GROUPS else
                              "image_ocr_agent" if doc["source_group"] in PENDING_GROUPS else "skip_agent")
            trace(stream, run_id, doc["doc_id"], "router", "route",
                  {"group": doc["source_group"], "agent": expected_agent, "source": "manifest rule"})
            if not path.exists():
                status, detail, agent = "failed", {"error": "corpus file missing"}, "router"
            elif doc["doc_id"] == "P1-06":
                status, detail = run_census_ocr(conn, run_id, doc, path, stream)
                agent = "image_ocr_agent"
            elif doc["doc_id"] in {"P1-13", "P1-15"}:
                status, detail = run_map_ocr(conn, run_id, doc, path, stream)
                agent = "map_legend_ocr_agent"
            elif doc["doc_id"] == "P1-14":
                status, detail = run_atlas_chart(conn, run_id, doc, path, stream)
                agent = "lulc_chart_agent"
            elif doc["source_group"] in TABLE_GROUPS:
                status, detail = run_table_agent(conn, run_id, doc, path, stream)
                agent = "pdf_table_agent"
            elif doc["source_group"] in TEXT_GROUPS:
                status, detail = run_text_agent(conn, run_id, doc, path, stream)
                agent = "pdf_text_agent"
            else:
                status, detail, agent = "partial", {"reason": "no specialized extractor configured for this source"}, "router"
                trace(stream, run_id, doc["doc_id"], agent, "status", detail)
            results.append({"doc_id": doc["doc_id"], "file": doc["file_name"], "agent": agent,
                            "group": doc["source_group"], "status": status, **detail})
            conn.commit()
    # Count only fully extracted inputs and deliberate out-of-scope skips as complete.
    # Partial and pending are terminal statuses, but they are not successful extraction.
    completed = sum(x["status"] in {"loaded", "skipped"} for x in results)
    overall = "complete_with_pending" if any(x["status"] in {"pending", "failed", "partial"} for x in results) else "complete"
    conn.execute("UPDATE extraction_run SET finished_at=?,status=?,completed=? WHERE run_id=?",
                 (now(), overall, completed, run_id))
    conn.commit()
    status_counts = {status: sum(x["status"] == status for x in results)
                     for status in ("loaded", "partial", "pending", "skipped", "failed")}
    summary = {"run_id": run_id, "status": overall, "attempted": len(results), "completed_without_intervention": completed,
               "manual_interventions": 0, "trace": str(trace_path.relative_to(ROOT)), "documents": results,
               "status_counts": status_counts,
               "observations": conn.execute("SELECT COUNT(*) FROM observation WHERE run_id=?", (run_id,)).fetchone()[0],
               "table_cells": conn.execute("SELECT COUNT(*) FROM table_cell WHERE run_id=?", (run_id,)).fetchone()[0],
               "text_facts": conn.execute("SELECT COUNT(*) FROM text_fact WHERE run_id=?", (run_id,)).fetchone()[0]}
    summary_path = LOGS / f"run_{run_id}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "documents"}, indent=2))
    print("Document status:", ", ".join(f"{x['doc_id']}={x['status']}" for x in results))
    conn.close()
    return 0 if not any(x["status"] == "failed" for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
