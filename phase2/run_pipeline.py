from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

from krutidev import split_bilingual_label
from source_paths import resolve_source_path

ROOT = Path(__file__).resolve().parents[1]
PHASE2 = Path(__file__).resolve().parent
MANIFEST = PHASE2 / "data" / "manifest.csv"
DB = PHASE2 / "db" / "agriculture_phase2.sqlite"
LOGS = PHASE2 / "logs"

TABLE_GROUPS = {"G1_AREA_PRODUCTION", "G2_BASIC_STATS", "G5_PRICES", "G7_LULC"}
TEXT_GROUPS = {"G3_ISLAND_PROFILES", "G4_NARRATIVE"}
PENDING_GROUPS = {"G6_CENSUS_IMAGE"}
SKIP_GROUPS = {"G8_RASTER_MAPS"}


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
        status = "loaded" if cells else "partial"
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
            expected_agent = ("pdf_table_agent" if doc["source_group"] in TABLE_GROUPS else
                              "pdf_text_agent" if doc["source_group"] in TEXT_GROUPS else
                              "pending_image_ocr" if doc["source_group"] in PENDING_GROUPS else "skip_agent")
            trace(stream, run_id, doc["doc_id"], "router", "route",
                  {"group": doc["source_group"], "agent": expected_agent, "source": "manifest rule"})
            if not path.exists():
                status, detail, agent = "failed", {"error": "corpus file missing"}, "router"
            elif doc["source_group"] in TABLE_GROUPS:
                status, detail = run_table_agent(conn, run_id, doc, path, stream)
                agent = "pdf_table_agent"
            elif doc["source_group"] in TEXT_GROUPS:
                status, detail = run_text_agent(conn, run_id, doc, path, stream)
                agent = "pdf_text_agent"
            elif doc["source_group"] in PENDING_GROUPS:
                status, detail, agent = "pending", {"reason": "OCR reader not available in this environment"}, "pending_image_ocr"
                trace(stream, run_id, doc["doc_id"], agent, "status", detail)
            else:
                status, detail, agent = "skipped", {"reason": "raster-map interpretation is out of scope"}, "skip_agent"
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
