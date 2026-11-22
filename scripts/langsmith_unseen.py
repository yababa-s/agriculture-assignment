"""Score unseen documents (no gold labels) and record the scores as a LangSmith experiment.

Run after scripts/run_pipeline.py --files ... . Nothing is re-extracted: the target reads the stored run.

  ./.venv/bin/python scripts/langsmith_unseen.py          # every unseen document (U01, U02, ...)
  ./.venv/bin/python scripts/langsmith_unseen.py U02

Reference-free scores per document (0..1):
  groundedness     share of stored numbers whose printed text is on the cited page of the file the agent read
  validation_pass  share of stored numbers that passed every validator check (no warning)
  load_rate        loaded / extracted (the rest were rejected by the validator)
Without LANGSMITH_API_KEY the same scores are printed locally.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from agri import config  # noqa: E402
from agri.db.db import connect  # noqa: E402
from scripts.check_unseen import trace_steps  # noqa: E402

_WS = re.compile(r"\s+")


def score_document(conn, did: str) -> dict:
    doc = conn.execute("SELECT * FROM document WHERE document_id=?", (did,)).fetchone()
    run = conn.execute("SELECT * FROM extraction_run WHERE document_id=? ORDER BY started_at DESC LIMIT 1", (did,)).fetchone()
    if not doc or not run:
        return {"document_id": did, "error": "not found"}
    ocr_pdf = next((s["payload"]["result"].get("path") for s in trace_steps(run)
                    if s["kind"] == "tool_result" and s["name"] == "make_searchable_pdf"
                    and isinstance(s["payload"].get("result"), dict)), None)
    read_path = ocr_pdf or doc["relative_path"]
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM observation WHERE run_id=? AND value IS NOT NULL AND value_raw <> ''", (run["run_id"],))]
    grounded = None
    if rows and str(read_path).lower().endswith(".pdf") and Path(read_path).exists():
        with pymupdf.open(read_path) as d:
            pages = {i + 1: _WS.sub("", p.get_text()) for i, p in enumerate(d)}
        grounded = sum(_WS.sub("", r["value_raw"]) in pages.get(r["page"] or 0, "") for r in rows) / len(rows)
    return {
        "document_id": did, "file_name": doc["file_name"], "agent": run["agent_id"], "status": run["status"],
        "extracted": run["n_extracted"], "loaded": run["n_loaded"], "rejected": run["n_rejected"],
        "groundedness": grounded,
        "validation_pass": (sum(r["validation"] != "warning" for r in rows) / len(rows)) if rows else None,
        "load_rate": (run["n_loaded"] / run["n_extracted"]) if run["n_extracted"] else None,
    }


def _metric(key):
    def evaluator(run, example) -> dict:
        return {"key": key, "score": run.outputs.get(key)}
    evaluator.__name__ = key
    return evaluator


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="*", help="document ids (default: all U## documents)")
    a = ap.parse_args()
    conn = connect(config.DB_PATH)
    ids = a.docs or [r[0] for r in conn.execute("SELECT document_id FROM document WHERE document_id LIKE 'U%' ORDER BY 1")]
    if not ids:
        sys.exit("no unseen documents yet: run scripts/run_pipeline.py --files <files> first")
    scores = [score_document(conn, did) for did in ids]
    for s in scores:
        print(f"{s['document_id']}  {s.get('file_name', '')}  " + "  ".join(
            f"{k} {v:.1%}" if isinstance(v, float) else f"{k} {v}"
            for k, v in s.items() if k in ("agent", "status", "groundedness", "validation_pass", "load_rate")))
    if not os.getenv("LANGSMITH_API_KEY"):
        print("\nLANGSMITH_API_KEY not set: scores above are local only.")
        return
    from langsmith import Client
    client = Client()
    name = f"{config.LANGSMITH_PROJECT}-unseen"
    ds = client.read_dataset(dataset_name=name) if client.has_dataset(dataset_name=name) else \
        client.create_dataset(name, description="unseen documents given at the demo (no gold labels)")
    have = {e.inputs.get("document_id") for e in client.list_examples(dataset_id=ds.id)}
    new = [s for s in scores if s["document_id"] not in have and "error" not in s]
    if new:
        client.create_examples(inputs=[{"document_id": s["document_id"], "file_name": s["file_name"]} for s in new],
                               dataset_id=ds.id)
    by_id = {s["document_id"]: s for s in scores}
    wanted = set(ids)
    examples = [e for e in client.list_examples(dataset_id=ds.id) if e.inputs.get("document_id") in wanted]
    res = client.evaluate(lambda inputs: by_id[inputs["document_id"]], data=examples,
                          evaluators=[_metric("groundedness"), _metric("validation_pass"), _metric("load_rate")],
                          experiment_prefix="unseen", max_concurrency=1)
    print(f"\nLangSmith experiment recorded: {res.experiment_name} (dataset {name})")


if __name__ == "__main__":
    main()
