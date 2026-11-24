"""Developer helper: run one agent on one document without the orchestrator and print a summary."""
import argparse, collections, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri.config import CORPUS_DIR, DB_PATH
from agri.db.db import connect
from agri.agents.base import AgentContext
from agri.agents.normalizer import Normalizer
from agri.agents.registry import AGENTS
from agri.llm.client import LLM
from agri.tracing import Tracer

ap = argparse.ArgumentParser()
ap.add_argument("doc_id"); ap.add_argument("agent"); ap.add_argument("--no-llm", action="store_true")
ap.add_argument("--show", type=int, default=8)
a = ap.parse_args()
conn = connect(DB_PATH)
doc = dict(conn.execute("SELECT * FROM document WHERE document_id=?", (a.doc_id,)).fetchone())
llm = LLM(backend="none" if a.no_llm else None)
tr = Tracer("dev_" + uuid.uuid4().hex[:6], a.agent, a.doc_id)
ctx = AgentContext(conn, llm, Normalizer(conn, llm, tr), tr, tr.run_id, "dev", doc, CORPUS_DIR / doc["relative_path"], use_llm=not a.no_llm)
res = AGENTS[a.agent]().run(ctx)
print("status", res.status, res.stats, res.notes[:5])
print("records", len(res.records), "unresolved", res.unresolved[:15])
c = collections.Counter((r["metric_id"], r["location_id"]) for r in res.records)
print(c.most_common(30))
for r in res.records[: a.show]:
    print({k: r[k] for k in ("metric_id", "commodity_id", "location_id", "period_label", "value", "unit_id", "page", "table_ref", "row_label", "col_label", "dims")})
print(tr.pretty(160)[-3000:])
conn.rollback()
