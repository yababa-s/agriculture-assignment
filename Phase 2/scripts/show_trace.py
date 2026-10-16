"""Print the decision/tool trace of a run for the demo.

  python scripts/show_trace.py D07                # latest run of a document
  python scripts/show_trace.py 3fa2c9d1e0b4       # a run id
  python scripts/show_trace.py D10 --records 5    # also show 5 loaded records with provenance

Each line: step, time, kind (decision | tool_call | tool_result | error | output), name,
by = model (LLM decided) | rule (fixed code) | tool | agent, and the payload.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.db.db import connect  # noqa: E402

COLORS = {"model": "\033[95m", "rule": "\033[94m", "tool": "\033[92m", "agent": "\033[0m"}
KIND_COLOR = {"error": "\033[91m", "output": "\033[93m"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="document id (D07) or run id")
    ap.add_argument("--records", type=int, default=0)
    ap.add_argument("--width", type=int, default=220)
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args()
    conn = connect(config.DB_PATH)
    run = conn.execute("SELECT * FROM extraction_run WHERE run_id=?", (a.target,)).fetchone() or conn.execute(
        "SELECT * FROM extraction_run WHERE document_id=? ORDER BY started_at DESC LIMIT 1", (a.target,)).fetchone()
    if not run:
        sys.exit(f"no run for {a.target}")
    doc = conn.execute("SELECT * FROM document WHERE document_id=?", (run["document_id"],)).fetchone()
    print(f"run {run['run_id']}  batch {run['batch_id']}  document {doc['document_id']} {doc['file_name']}")
    print(f"agent {run['agent_id']}  model {run['model_name'] or '-'}  adapter {run['adapter'] or '-'}  status {run['status']}"
          f"  attempts {run['attempts']}  extracted {run['n_extracted']}  loaded {run['n_loaded']}  rejected {run['n_rejected']}"
          f"  llm_calls {run['n_llm_calls']}")
    print(f"source: {doc['modality']}, languages {doc['languages']}, legacy font {bool(doc['legacy_font'])}, group {doc['source_group']}\n")
    steps = [json.loads(x) for x in (config.ROOT / run["trace_path"]).read_text().splitlines()]
    counts = {"model": 0, "rule": 0}
    for s in steps:
        if s["kind"] == "decision":
            counts[s["by"]] = counts.get(s["by"], 0) + 1
        payload = json.dumps(s["payload"], ensure_ascii=False, default=str)
        if len(payload) > a.width:
            payload = payload[:a.width] + "…"
        c = "" if a.no_color else KIND_COLOR.get(s["kind"], COLORS.get(s["by"], ""))
        r = "" if a.no_color else "\033[0m"
        print(f"{c}[{s['i']:>3}] {s['t']:>7.2f}s {s['kind']:<11} {s['name']:<26} by={s['by']:<5}{r} {payload}")
    print(f"\ndecisions by model: {counts.get('model', 0)}   decisions by rule: {counts.get('rule', 0)}")
    if a.records:
        print("\nloaded records (provenance):")
        for r in conn.execute("SELECT metric_id, commodity_id, location_id, period_label, value, unit_id, page, table_ref, "
                              "row_label, col_label, validation FROM observation WHERE run_id=? LIMIT ?", (run["run_id"], a.records)):
            print("  ", dict(r))
        for f in conn.execute("SELECT subject, predicate, object, page, evidence FROM text_fact WHERE run_id=? LIMIT ?",
                              (run["run_id"], a.records)):
            print("  ", dict(f))


if __name__ == "__main__":
    main()
