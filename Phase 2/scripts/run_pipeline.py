"""Run the full pipeline over the corpus (or selected documents / unseen files).

Examples
  python scripts/run_pipeline.py --fresh                 # rebuild DB and process all 20 corpus files
  python scripts/run_pipeline.py --docs D02 D10          # only these documents
  python scripts/run_pipeline.py --files ~/Downloads/new.pdf   # unseen document: routed by fingerprint + LLM
  python scripts/run_pipeline.py --no-llm                # rules-only ablation
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.db.db import connect, init_db  # noqa: E402
from agri.llm.client import LLM  # noqa: E402
from agri.orchestrator.graph import Orchestrator, corpus_documents, register_unseen  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="recreate the database before running")
    ap.add_argument("--docs", nargs="*", help="document ids from the manifest")
    ap.add_argument("--files", nargs="*", help="paths of unseen documents")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--adapter", default=None, help="LoRA adapter directory")
    ap.add_argument("--force-llm-routing", action="store_true", help="route every file with the model, ignoring the manifest")
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()

    conn = init_db(a.db, fresh=a.fresh) if a.fresh or not Path(a.db).exists() else connect(a.db)
    if not a.fresh:
        init_db(a.db)  # idempotent: ensures schema + reference data
    llm = LLM(backend="none" if a.no_llm else None, adapter_path=a.adapter)
    docs = []
    if a.files:
        docs += [register_unseen(conn, f) for f in a.files]
    if a.docs or not a.files:
        docs += corpus_documents(conn, a.docs)
    orch = Orchestrator(conn, llm, use_llm=not a.no_llm, force_llm_routing=a.force_llm_routing)
    t0 = time.time()
    out = orch.run(docs)
    out["elapsed_s"] = round(time.time() - t0, 1)
    out["model"] = llm.label if not a.no_llm else "none (rules only)"
    path = config.ROOT / "logs" / f"batch_{out['batch_id']}.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nbatch {out['batch_id']}  {len(docs)} documents  {out['elapsed_s']}s  model={out['model']}")
    print(f"{'doc':<5}{'agent':<24}{'route':<7}{'status':<13}{'try':>4}{'extr':>7}{'load':>7}{'rej':>6}{'llm':>5}")
    for d in out["documents"]:
        print(f"{d['document_id']:<5}{d['agent']:<24}{(d['routed_by'] or ''):<7}{d['status']:<13}{d['attempts']:>4}"
              f"{d['extracted']:>7}{d['loaded']:>7}{d['rejected']:>6}{d['llm_calls']:>5}")
    print(f"summary -> {path}")


if __name__ == "__main__":
    main()
