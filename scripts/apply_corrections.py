"""Post-load corrections found by scripts/audit_db.py. Idempotent; every change is logged in the `correction` table.

Rules (each one was traced to a concrete extraction defect or a publisher error, see docs/data_quality.md):
  R1  mapping   'Curry Banana' (a cooking-banana vegetable) was fuzzy-matched to banana -> plantain_green;
                'Sax Clove' (undecoded Hindi prefix) stayed unmapped -> clove
  R2  unit      the printed label states the unit and it disagrees with the stored unit ('(ha.)' stored as sq km)
  R3  metric    rows from the seedlings and pesticide blocks were stored as fertilizer consumption -> rejected
  R4  layout    rows whose label is a year or a district name come from mis-read transposed sub-tables -> rejected
  R5  item      area / production / yield rows with no identified crop (category totals, mis-read rows) -> rejected
  R6  item      'Other fruits', 'Other root crop' ... were stored as the category total -> marked as the 'other' item
  R7  bounds    an island's cultivated or forest area larger than the island itself (publisher decimal slip) -> rejected
  R8  unit      seed rows printed '(MT)' under a '(Kg.)' block header: source is inconsistent -> warning only
  R9  mapping   two different printed rows in one table mapped to the same crop ('Smooth Gourd' and 'Ridge Gourd',
                'water spinach' and 'Spinach'): the row that is only an alias is a separate item -> marked as an item;
                if no row is the crop itself ('HYV' / 'Paddy Traditional') each row is marked as a variety
  R11 place     machinery tables (D04-D06): the 'N & M Andaman' column was stored as Nicobar and the 'Nicobar'
                column as the whole UT (a one-column shift) -> location re-derived from the printed column header
  R12 place     a district-wise value whose column header was not read (blank) was stored at the UT -> rejected
  R13 unit      an area stored in sq km that is larger than the whole UT (8,249 sq km) cannot be sq km: the land-use
                tables print hectares (824,900 ha = 8,249 sq km) -> unit set to ha
  R14 item      land-utilisation rows 'Total Cropped Area', 'Total Food Crops', 'Total Non Food Crops' were all stored
                as the plain total of the table -> each kept as its own item
  R10 item      'Total (A+B)' (fruits including citrus) was stored as the citrus total -> marked as a separate total

Rejected rows stay in the database with validation='error' and a note; query tools ignore them.

  python scripts/apply_corrections.py [--db PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402

DISTRICT_LABEL = re.compile(r"^(south andaman|n ?& ?m andaman|north (&|and) middle andaman|nicobar)$", re.I)
YEAR_LABEL = re.compile(r"^\d{4}-\d{2}$")
UT_AREA_SQ_KM = 8249     # Andaman & Nicobar Islands, total geographical area


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(config.DB_PATH))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = sqlite3.connect(a.db)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS correction (corr_id INTEGER PRIMARY KEY AUTOINCREMENT, obs_id INTEGER NOT NULL,
                 rule TEXT NOT NULL, field TEXT NOT NULL, old_value TEXT, new_value TEXT, reason TEXT NOT NULL,
                 applied_at TEXT NOT NULL, UNIQUE (obs_id, rule, field))""")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    counts: dict[str, int] = {}

    def change(obs_id: int, rule: str, field: str, new, reason: str) -> None:
        old = c.execute(f"SELECT {field} FROM observation WHERE obs_id=?", (obs_id,)).fetchone()[0]
        if str(old) == str(new):
            return
        cur = c.execute("INSERT OR IGNORE INTO correction (obs_id, rule, field, old_value, new_value, reason, applied_at) "
                        "VALUES (?,?,?,?,?,?,?)", (obs_id, rule, field, None if old is None else str(old), str(new), reason, now))
        if cur.rowcount:
            c.execute(f"UPDATE observation SET {field}=? WHERE obs_id=?", (new, obs_id))
            counts[rule] = counts.get(rule, 0) + 1

    def reject(obs_id: int, rule: str, reason: str) -> None:
        change(obs_id, rule, "validation", "error", reason)
        change(obs_id, rule, "validation_note", reason, reason)

    rows = [dict(r) for r in c.execute("SELECT * FROM observation")]
    geo = {(r["location_id"], r["period_label"]): r["value"] for r in c.execute(
        "SELECT location_id, period_label, value FROM observation WHERE metric_id='geographical_area' AND value IS NOT NULL")}
    for r in rows:
        label = (r["row_label"] or "").strip()
        lab_l = label.lower()
        dims = json.loads(r["dims"] or "{}")
        item = str(dims.get("item", "")).strip()
        group = str(dims.get("group", "")).lower()
        crop_metric = r["metric_id"] in ("area_cultivated", "production", "yield")
        # R1 mapping
        if "curry banana" in lab_l and r["commodity_id"] != "plantain_green":
            change(r["obs_id"], "R1", "commodity_id", "plantain_green", "'Curry Banana' is the cooking-banana vegetable, not banana")
            r["commodity_id"] = "plantain_green"
        if re.search(r"\bclove\b", lab_l) and r["commodity_id"] is None and crop_metric:
            change(r["obs_id"], "R1", "commodity_id", "clove", "label 'Sax Clove' = clove with an undecoded Hindi prefix")
            r["commodity_id"] = "clove"
        # R2 unit stated in the label
        both = f"{label} {r['col_label'] or ''}".lower()
        if r["unit_id"] == "sq_km" and re.search(r"\(\s*ha\b|hectare", both):
            change(r["obs_id"], "R2", "unit_id", "ha", "label states hectares; stored as sq km (100x error)")
        elif r["unit_id"] == "ha" and re.search(r"sq\.?\s*km", both) and r["metric_id"] != "area_cultivated":
            change(r["obs_id"], "R2", "unit_id", "sq_km", "label states sq km; stored as ha")
        # R13 physically impossible area for sq km
        if r["unit_id"] == "sq_km" and r["value"] is not None and r["value"] > UT_AREA_SQ_KM * 1.01:
            change(r["obs_id"], "R13", "unit_id", "ha", f"{r['value']} sq km is larger than the whole UT "
                                                         f"({UT_AREA_SQ_KM} sq km); the table prints hectares")
        # R14 several different land-utilisation totals stored as the one plain value
        if r["metric_id"] == "land_use_area" and "item" not in dims and label:
            dims["item"] = label
            change(r["obs_id"], "R14", "dims", json.dumps(dims, sort_keys=True, ensure_ascii=False),
                   f"'{label}' is one line of the land-utilisation table, not the table total")
        # R3 wrong metric for the block
        if r["metric_id"] == "fertilizer_consumption" and ("seedling" in group or "pesticide" in group):
            reject(r["obs_id"], "R3", f"row from the '{dims.get('group')}' block stored as fertilizer consumption")
            continue
        # R4 mis-read transposed sub-tables
        if YEAR_LABEL.match(label) or YEAR_LABEL.match(item) \
                or (group.startswith("district-wise") and (DISTRICT_LABEL.match(item) or YEAR_LABEL.match(item))) \
                or (crop_metric and DISTRICT_LABEL.match(label)):
            reject(r["obs_id"], "R4", "label is a year or a district name: row comes from a mis-read transposed sub-table")
            continue
        # R5 crop rows without a crop
        if crop_metric and r["commodity_id"] is None and r["value"] is not None:
            reject(r["obs_id"], "R5", "no crop identified (category total or mis-read row)")
            continue
        # R6 'Other ...' rows stored as the category total
        if (lab_l.startswith("other") or lab_l.startswith("misc")) and (r["commodity_id"] or "").startswith("agg_") and "item" not in dims:
            dims["item"] = label
            change(r["obs_id"], "R6", "dims", json.dumps(dims, sort_keys=True, ensure_ascii=False),
                   f"'{label}' is the residual 'other' item, not the category total")
        # R7 part larger than the island
        if r["metric_id"] in ("area_under_cultivation", "forest_area") and r["value"] is not None and r["unit_id"] == "sq_km":
            g = geo.get((r["location_id"], r["period_label"]))
            if g and r["value"] > g * 1.01 and r["location_id"].startswith("ISL_"):
                reject(r["obs_id"], "R7", f"printed {r['value_raw']} sq km exceeds the island's area of {g} sq km "
                                          "(publisher decimal slip; other editions print 0.01818 / 0.1818)")
                continue
        # R8 source inconsistency, warning only
        if r["metric_id"] == "seed_distributed" and "(mt)" in lab_l and r["unit_id"] == "kg" and r["validation"] == "ok":
            change(r["obs_id"], "R8", "validation", "warning", "row says (MT) but the block header says (Kg.)")
            change(r["obs_id"], "R8", "validation_note", "row label says (MT) but the block header says (Kg.); unit uncertain", "")
    # R11 / R12: the printed district column header decides the place
    col_place = [(re.compile(r"south andaman", re.I), "AN_SA"),
                 (re.compile(r"n\s*&\s*m\b|middle andaman", re.I), "AN_NMA"),
                 (re.compile(r"nicobar", re.I), "AN_NIC")]
    district_rows = set()
    for r in c.execute("SELECT * FROM observation WHERE validation != 'error' AND col_label LIKE 'District-wise%'"):
        r = dict(r)
        district_rows.add((r["document_id"], r["page"], r["row_label"], r["metric_id"], r["period_label"]))
        english = re.sub(r"[^A-Za-z&\s]", " ", r["col_label"].split("|", 1)[-1])
        for pat, loc in col_place:
            if pat.search(english):
                if r["location_id"] != loc:
                    change(r["obs_id"], "R11", "location_id", loc,
                           f"column header '{r['col_label']}' names {loc}; the row was stored at {r['location_id']}")
                break
    for r in c.execute("SELECT * FROM observation WHERE validation != 'error' AND location_id='AN' "
                       "AND (col_label IS NULL OR TRIM(col_label)='')"):
        r = dict(r)
        sib = c.execute("SELECT 1 FROM observation WHERE document_id=? AND page=? AND row_label=? AND metric_id=? "
                        "AND location_id IN ('AN_SA','AN_NMA','AN_NIC') AND obs_id != ?",
                        (r["document_id"], r["page"], r["row_label"], r["metric_id"], r["obs_id"])).fetchone()
        if sib:
            reject(r["obs_id"], "R12", "district-wise value whose column header was not read; stored at the UT by mistake")
    # R9 / R10 need the whole table: group live rows by (document, page, metric, location, period, commodity)
    names = {r[0]: r[1].lower() for r in c.execute("SELECT commodity_id, name FROM commodity")}
    live = [dict(r) for r in c.execute("SELECT * FROM observation WHERE validation != 'error' AND commodity_id IS NOT NULL")]
    tables: dict[tuple, list] = {}
    for r in live:
        if "item" in json.loads(r["dims"] or "{}"):
            continue
        tables.setdefault((r["document_id"], r["page"], r["metric_id"], r["location_id"], r["period_label"],
                           r["commodity_id"]), []).append(r)
    for rs in tables.values():
        labels = {(x["row_label"] or "").strip() for x in rs}
        if len(labels) < 2:
            continue
        canon = names.get(rs[0]["commodity_id"], "")

        def is_canon(lab: str) -> bool:
            return lab.lower().split(" (")[0].strip() == canon.split(" (")[0].strip()
        vals = [x["value"] for x in rs if x["value"] is not None]
        if vals and max(vals) - min(vals) <= 0.01 * max(abs(v) for v in vals):
            continue                      # same number printed twice (e.g. 'Pulses' and 'Total'): no conflict
        has_canon = any(is_canon((x["row_label"] or "").strip()) for x in rs)
        for x in rs:
            lab = (x["row_label"] or "").strip()
            composite = re.match(r"^total\s*\(a\s*\+\s*b\)", lab, re.I)
            d = json.loads(x["dims"] or "{}")
            if composite or (has_canon and not is_canon(lab)):
                d["item"] = lab           # a different item printed next to the main one
                rule = "R10" if composite else "R9"
                why = f"'{lab}' is printed as its own row next to '{canon}'; kept as a separate item"
            elif not has_canon and "variety" not in d and not any(
                    re.match(r"^total\s*\(a\s*\+\s*b\)", (y["row_label"] or "").strip(), re.I) for y in rs):
                d["variety"] = lab        # e.g. 'HYV' and 'Paddy Traditional', 'Coffee Powder' and 'Nescafe'
                rule, why = "R9", f"'{lab}' is one of several printed varieties of {canon}; kept as a variety"
            else:
                continue
            change(x["obs_id"], rule, "dims", json.dumps(d, sort_keys=True, ensure_ascii=False), why)
    # root-cause alias fix so a re-extraction maps 'Curry Banana' correctly
    c.execute("UPDATE alias SET entity_id='plantain_green', origin='manual' WHERE entity_type='commodity' AND alias='curry banana'")
    c.execute("INSERT OR IGNORE INTO alias VALUES ('sax clove','commodity','clove','en','manual')")
    c.execute("DELETE FROM alias WHERE entity_type='commodity' AND alias IN ('total (a+b)')")
    if a.dry_run:
        c.rollback()
    else:
        c.commit()
    total = c.execute("SELECT COUNT(*) FROM correction").fetchone()[0]
    print(f"{'(dry run) ' if a.dry_run else ''}changes this run by rule: {counts}  | corrections logged in total: {total}")
    print("rejected rows:", c.execute("SELECT COUNT(*) FROM observation WHERE validation='error'").fetchone()[0])


if __name__ == "__main__":
    main()
