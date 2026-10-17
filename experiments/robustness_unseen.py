"""Run the robustness test documents (scripts/make_test_unseen.py) through the full pipeline as UNSEEN
files and score each against the values already known from its source corpus file.

Precision = extracted values that equal a known value / extracted values
Recall    = known values recovered / known values in scope
A tuple is (metric, commodity, location, period, value); prices use (metric, commodity, period, value).

  ./.venv/bin/python experiments/robustness_unseen.py      -> eval/results/robustness_unseen.json
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.db.db import connect, init_db  # noqa: E402
from agri.llm.client import LLM  # noqa: E402
from agri.orchestrator.graph import Orchestrator, register_unseen  # noqa: E402
from scripts.make_test_unseen import CROPS_HI, ZONES_HI  # noqa: E402

T = config.ROOT / "data" / "test_unseen"
CASES = [
    ("T1 scanned English tables", "scan_area_production_2025-26.pdf", "D02", None, "matrix_table_agent"),
    ("T2 photo of a price table", "photo_prices_jan2024.png", "D12", 1, "price_table_agent"),
    ("T3 Unicode Hindi table", "hindi_area_production_2025-26.pdf", "D02", "hindi_subset", "matrix_table_agent"),
    ("T4 scanned bilingual Hindi page", "scan_basic_statistics_2024-25.pdf", "D06", 1, "bilingual_table_agent"),
    ("T5 map image", "map_india_lulc.png", None, None, "skip"),
    ("T6 Hindi PDF with broken text layer", "hindi_broken_textlayer_2025-26.pdf", "D02", "hindi_subset", "matrix_table_agent"),
]


def key(r, price: bool):
    v = round(float(r["value"]), 4)
    return (r["metric_id"], r["commodity_id"], r["period_label"], v) if price else \
        (r["metric_id"], r["commodity_id"], r["location_id"], r["period_label"], v)


def truth(conn, doc: str, scope) -> set:
    q = "SELECT * FROM observation WHERE document_id=? AND value IS NOT NULL AND commodity_id IS NOT NULL"
    rows = [dict(r) for r in conn.execute(q, (doc,))]
    price = doc in ("D11", "D12", "D13")
    if isinstance(scope, int):
        rows = [r for r in rows if r["page"] == scope]
    if scope == "hindi_subset":
        crops, zones = {c for c, _ in CROPS_HI}, {z for z, _ in ZONES_HI}
        rows = [r for r in rows if r["commodity_id"] in crops and r["location_id"] in zones
                and r["metric_id"] in ("area_cultivated", "production") and r["page"] == 1]
    return {key(r, price) for r in rows}


def main() -> None:
    tmp_db = config.ROOT / "db" / "robustness_tmp.sqlite"
    shutil.copy(config.DB_PATH, tmp_db)
    conn = init_db(tmp_db)
    llm = LLM(adapter_path="adapters/34_AN_qlora_v1")
    docs = [register_unseen(conn, str(T / f)) for _, f, *_ in CASES]
    t0 = time.time()
    out = Orchestrator(conn, llm).run(docs, batch_id="ROBUSTNESS_" + time.strftime("%Y%m%d_%H%M%S"))
    elapsed = round(time.time() - t0, 1)
    results = []
    for (name, fname, src, scope, expected_agent), doc, run in zip(CASES, docs, out["documents"]):
        got_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM observation WHERE run_id=? AND value IS NOT NULL AND commodity_id IS NOT NULL", (run["run_id"],))]
        res = {"case": name, "file": fname, "doc": doc["document_id"], "agent": run["agent"], "expected_agent": expected_agent,
               "routed_ok": run["agent"] == expected_agent, "status": run["status"], "loaded": run["loaded"],
               "llm_calls": run["llm_calls"]}
        steps = [json.loads(x) for x in (config.ROOT / conn.execute(
            "SELECT trace_path FROM extraction_run WHERE run_id=?", (run["run_id"],)).fetchone()[0]).read_text().splitlines()]
        ocr = next((s["payload"] for s in steps if s["name"] == "ocr_to_searchable_pdf"), None)
        if ocr:
            res["ocr"] = ocr
        if src:
            gold = truth(conn, src, scope)
            price = src in ("D11", "D12", "D13")
            got = {key(r, price) for r in got_rows}
            tp = len(got & gold)
            res.update({"known_values": len(gold), "extracted_values": len(got), "correct": tp,
                        "precision": round(tp / max(1, len(got)), 3), "recall": round(tp / max(1, len(gold)), 3)})
        results.append(res)
        print({k: v for k, v in res.items() if k != "ocr"})
    report = {"batch": out["batch_id"], "elapsed_s": elapsed, "model": llm.label, "cases": results}
    (config.RESULTS_DIR / "robustness_unseen.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    conn.close()
    tmp_db.unlink()
    print(f"-> {config.RESULTS_DIR / 'robustness_unseen.json'}  ({elapsed}s)")


if __name__ == "__main__":
    main()
