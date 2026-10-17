"""Live check of unseen documents after scripts/run_pipeline.py --files ... (use during the demo).

  ./.venv/bin/python scripts/check_unseen.py            # every unseen document (U01, U02, ...)
  ./.venv/bin/python scripts/check_unseen.py U02 --samples 8

For each document: how it was routed and read (OCR engine if it was a scan), status and counts,
GROUNDEDNESS (share of extracted numbers whose printed text is on the cited page of the file the
agent read) and a few sample facts with page / row / column to compare against the PDF by eye.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from agri import config  # noqa: E402
from agri.db.db import connect  # noqa: E402

_WS = re.compile(r"\s+")


def trace_steps(run) -> list[dict]:
    p = config.ROOT / (run["trace_path"] or "")
    return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="*", help="document ids (default: all U## documents)")
    ap.add_argument("--samples", type=int, default=5)
    a = ap.parse_args()
    conn = connect(config.DB_PATH)
    ids = a.docs or [r[0] for r in conn.execute("SELECT document_id FROM document WHERE document_id LIKE 'U%' ORDER BY 1")]
    if not ids:
        sys.exit("no unseen documents yet: run scripts/run_pipeline.py --files <files> first")
    total_checked = total_found = 0
    for did in ids:
        doc = conn.execute("SELECT * FROM document WHERE document_id=?", (did,)).fetchone()
        run = conn.execute("SELECT * FROM extraction_run WHERE document_id=? ORDER BY started_at DESC LIMIT 1", (did,)).fetchone()
        if not doc or not run:
            print(f"\n{did}: not found")
            continue
        steps = trace_steps(run)
        route = next((s for s in steps if s["kind"] == "decision" and s["name"] == "route"), {})
        ocr = next((s["payload"] for s in steps if s["name"] == "ocr_to_searchable_pdf"), None)
        ocr_pdf = next((s["payload"]["result"].get("path") for s in steps
                        if s["kind"] == "tool_result" and s["name"] == "make_searchable_pdf"
                        and isinstance(s["payload"].get("result"), dict)), None)
        read_path = ocr_pdf or doc["relative_path"]
        print(f"\n{'=' * 100}\n{did}  {doc['file_name']}  ({doc['languages']}, {doc['modality']})")
        print(f"  routed to {run['agent_id']} by {route.get('by', '?')}: {route.get('payload', {}).get('reason', '')}")
        if ocr:
            print(f"  scanned -> OCR: {ocr.get('reason')}; engines {ocr.get('engines')}; mean confidence {ocr.get('mean_conf')}")
        print(f"  status {run['status']}  extracted {run['n_extracted']}  loaded {run['n_loaded']}  rejected {run['n_rejected']}"
              f"  LLM calls {run['n_llm_calls']}")
        if run["error"]:
            print(f"  notes: {run['error'][:240]}")
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM observation WHERE run_id=? AND value IS NOT NULL AND value_raw <> ''", (run["run_id"],))]
        found = 0
        if rows and str(read_path).lower().endswith(".pdf") and Path(read_path).exists():
            with pymupdf.open(read_path) as d:
                pages = {i + 1: _WS.sub("", p.get_text()) for i, p in enumerate(d)}
            found = sum(_WS.sub("", r["value_raw"]) in pages.get(r["page"] or 0, "") for r in rows)
            total_checked += len(rows)
            total_found += found
            print(f"  GROUNDEDNESS: {found}/{len(rows)} numbers found on their cited page ({found / len(rows):.1%})")
        warn = sum(1 for r in rows if r["validation"] == "warning")
        if warn:
            print(f"  validation warnings: {warn}")
        print(f"  sample facts (check against the PDF):")
        for r in random.Random(34).sample(rows, min(a.samples, len(rows))):
            what = r["commodity_id"] or json.loads(r["dims"]).get("item") or ""
            print(f"    p{r['page']:<3} {r['metric_id']:<18} {what:<16} {r['location_id']:<16} {r['period_label']:<13} "
                  f"= {r['value_raw']:<10} | row '{(r['row_label'] or '')[:28]}' col '{(r['col_label'] or '')[:34]}'")
    if total_checked:
        print(f"\nOVERALL GROUNDEDNESS: {total_found}/{total_checked} ({total_found / total_checked:.1%})")


if __name__ == "__main__":
    main()
