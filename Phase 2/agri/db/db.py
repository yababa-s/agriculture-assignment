"""SQLite access layer: init, reference-data seeding, and provenance-aware inserts."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from agri.config import DB_PATH, MANIFEST_PATH
from agri.db import seed
from agri.sources import SOURCES

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

AGENTS = {
    "router_agent": "Supervisor: inspects a document and routes it to an extraction agent",
    "matrix_table_agent": "English matrix tables (crop x location x metric) from digital PDFs",
    "bilingual_table_agent": "Bilingual Hindi (Kruti Dev) + English statistical tables",
    "price_table_agent": "Monthly comparative retail price tables",
    "island_profile_agent": "LLM key-value extraction from island statistical profiles",
    "narrative_agent": "LLM extraction of scheme finances and facts from narrative reports",
    "image_table_agent": "OCR + LLM structuring of table screenshots",
    "lulc_agent": "Land use / land cover statistics tables",
    "normalizer_agent": "Entity resolution of crops, locations, metrics, units",
    "validator_agent": "Rule-based validation, cross-checks and dedup",
}
AGENT_VERSION = "0.2.0"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | str = DB_PATH, fresh: bool = False) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh and path.exists():
        path.unlink()
    conn = connect(path)
    conn.executescript(SCHEMA_PATH.read_text())
    seed_reference(conn)
    load_manifest(conn)
    conn.commit()
    return conn


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("\n", " ").split())


def seed_reference(conn: sqlite3.Connection) -> None:
    for sid, s in SOURCES.items():
        conn.execute("INSERT OR REPLACE INTO source VALUES (?,?,?,?,?)",
                     (sid, s["name"], s["portal_url"], s["source_type"], s["license"]))
    for aid, desc in AGENTS.items():
        conn.execute("INSERT OR REPLACE INTO agent VALUES (?,?,?)", (aid, desc, AGENT_VERSION))
    for uid, sym, dim, base, factor in seed.UNITS:
        conn.execute("INSERT OR REPLACE INTO unit VALUES (?,?,?,?,?)", (uid, sym, dim, None, factor))
    for uid, sym, dim, base, factor in seed.UNITS:
        conn.execute("UPDATE unit SET base_unit_id=? WHERE unit_id=?", (base, uid))
    for mid, name, domain, unit, desc in seed.METRICS:
        conn.execute("INSERT OR REPLACE INTO metric VALUES (?,?,?,?,?)", (mid, name, domain, unit, desc))
    for lid, name, hi, level, parent, aliases in seed.LOCATIONS:
        conn.execute("INSERT INTO location (location_id,name,name_hi,level,parent_id) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(location_id) DO UPDATE SET name=excluded.name, level=excluded.level, parent_id=excluded.parent_id, "
                     "name_hi=COALESCE(location.name_hi, excluded.name_hi)", (lid, name, hi, level, parent))
        _aliases(conn, "location", lid, [name] + aliases + ([hi] if hi else []))
    for lid, name, hi, parent, aliases in seed.ISLANDS:
        conn.execute("INSERT INTO location (location_id,name,name_hi,level,parent_id) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(location_id) DO UPDATE SET name=excluded.name, parent_id=excluded.parent_id",
                     (lid, name, hi, "island", parent))
        _aliases(conn, "location", lid, [name] + aliases + [hi])
    for cid, name, cat, aliases in seed.COMMODITIES:
        # upsert: re-seeding must not wipe Hindi names learned from decoded documents
        conn.execute("INSERT INTO commodity VALUES (?,?,?,?,?) ON CONFLICT(commodity_id) DO UPDATE SET "
                     "name=excluded.name, category=excluded.category, is_aggregate=excluded.is_aggregate",
                     (cid, name, None, cat, 1 if cat == "aggregate" else 0))
        _aliases(conn, "commodity", cid, [name] + aliases)
    for uid, aliases in seed.UNIT_ALIASES.items():
        _aliases(conn, "unit", uid, aliases)
    for mid, aliases in seed.METRIC_ALIASES.items():
        _aliases(conn, "metric", mid, aliases)


def _aliases(conn, etype: str, eid: str, aliases: list[str], origin: str = "seed") -> None:
    for a in aliases:
        if not a:
            continue
        lang = "hi" if any("ऀ" <= ch <= "ॿ" for ch in a) else "en"
        conn.execute("INSERT OR IGNORE INTO alias VALUES (?,?,?,?,?)", (_norm(a), etype, eid, lang, origin))


def add_alias(conn, etype: str, eid: str, alias: str, origin: str = "llm") -> None:
    _aliases(conn, etype, eid, [alias], origin)


def load_manifest(conn: sqlite3.Connection, manifest: Path = MANIFEST_PATH) -> None:
    if not manifest.exists():
        return
    with open(manifest) as f:
        for r in csv.DictReader(f):
            upsert_document(conn, r)


def upsert_document(conn, r: dict) -> None:
    conn.execute(
        """INSERT INTO document (document_id, source_id, file_name, relative_path, document_url, source_group,
               period_label, modality, languages, scripts, legacy_font, pages, sha256, collection_date, license)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(document_id) DO UPDATE SET document_url=excluded.document_url, collection_date=excluded.collection_date, source_group=excluded.source_group,
               modality=excluded.modality,
               languages=excluded.languages, scripts=excluded.scripts, legacy_font=excluded.legacy_font""",
        (r["doc_id"], r["source_id"], r["file_name"], r.get("relative_path"), r.get("document_url"), r["source_group"],
         r.get("period"), r["modality"], r["languages"], r.get("scripts"),
         1 if str(r.get("legacy_font_encoding")).lower() in ("true", "1") else 0,
         int(r.get("pages") or 0), r["sha256"], r.get("collection_date"), r.get("license")),
    )


def dedup_key(rec: dict) -> str:
    parts = [rec.get(k) for k in ("metric_id", "commodity_id", "location_id", "period_label", "document_id",
                                    "page", "table_ref", "row_label", "col_label")]
    parts.append(json.dumps(rec.get("dims") or {}, sort_keys=True, ensure_ascii=False))
    return hashlib.sha1("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


OBS_COLS = ["metric_id", "commodity_id", "location_id", "period_label", "period_type", "period_start", "period_end",
            "season", "dims", "value", "unit_id", "value_raw", "unit_raw", "missing_reason", "is_total_row",
            "document_id", "page", "table_ref", "row_label", "col_label", "run_id", "agent_id", "confidence",
            "validation", "validation_note", "dedup_key"]


def insert_observations(conn, records: list[dict]) -> tuple[int, int]:
    """Insert records; returns (inserted, duplicates_skipped)."""
    inserted = dup = 0
    for rec in records:
        row = dict(rec)
        row["dims"] = json.dumps(row.get("dims") or {}, sort_keys=True, ensure_ascii=False)
        row["dedup_key"] = row.get("dedup_key") or dedup_key(rec)
        cur = conn.execute(
            f"INSERT OR IGNORE INTO observation ({','.join(OBS_COLS)}) VALUES ({','.join('?' * len(OBS_COLS))})",
            [row.get(c) for c in OBS_COLS],
        )
        if cur.rowcount:
            inserted += 1
        else:
            dup += 1
    return inserted, dup


def insert_text_facts(conn, facts: list[dict]) -> int:
    n = 0
    for f in facts:
        key = hashlib.sha1("|".join(str(f.get(k)) for k in ("subject", "predicate", "object", "document_id", "page")).encode()).hexdigest()
        cur = conn.execute(
            """INSERT OR IGNORE INTO text_fact (subject,predicate,object,location_id,period_label,document_id,page,
                   evidence,run_id,agent_id,dedup_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (f["subject"], f["predicate"], f["object"], f.get("location_id"), f.get("period_label"), f["document_id"],
             f.get("page"), f["evidence"], f["run_id"], f["agent_id"], key))
        n += cur.rowcount
    return n


def insert_rejected(conn, run_id: str, payload: dict, reason: str) -> None:
    conn.execute("INSERT INTO rejected_record (run_id,payload,reason) VALUES (?,?,?)",
                 (run_id, json.dumps(payload, ensure_ascii=False, default=str), reason))


def upsert_chunks(conn, document_id: str, pages: list[str]) -> None:
    for i, text in enumerate(pages, start=1):
        conn.execute("INSERT OR REPLACE INTO document_chunk (document_id,page,text) VALUES (?,?,?)", (document_id, i, text))
