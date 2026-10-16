"""LangGraph orchestration: supervisor/router + per-document pipeline with validation-driven retries.

    START -> intake --(queue empty)--> finish -> END
               |
               v
             route --(skip)--> load(skip) --> intake
               |
               v
            extract -> validate --(error_rate > threshold & LLM agent & attempts left)--> extract (retry with feedback)
                                   \\--> load -> intake

State passed between nodes is plain data (doc row, routing decision, agent result,
validation summary). Each document gets its own extraction_run row and trace file.
Processing is complete when the queue is empty and every document has a terminal
status (loaded | partial | failed | needs_review | skipped).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import traceback
import uuid
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agri import config
from agri.agents.base import AgentContext, AgentResult
from agri.agents.normalizer import Normalizer
from agri.agents.registry import AGENTS
from agri.agents.router import RouterAgent, guess_group
from agri.agents.validator import Validator
from agri.db.db import insert_observations, insert_rejected, insert_text_facts, upsert_chunks, upsert_document
from agri.llm.client import LLM
from agri.tools.lang import detect_languages
from agri.tools.pdf_tools import page_text_unicode, page_texts
from agri.tracing import Tracer

RETRY_ERROR_RATE = 0.2


class PipelineState(TypedDict, total=False):
    batch_id: str
    queue: list[dict]          # documents still to process
    current: dict | None       # document row being processed
    run_id: str
    agent_id: str
    routed_by: str
    attempt: int
    result: dict               # serialised AgentResult summary (records kept on the side)
    validation: dict
    done: list[dict]           # per-document summaries
    options: dict
    retry: bool


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Orchestrator:
    def __init__(self, conn, llm: LLM | None = None, use_llm: bool = True, force_llm_routing: bool = False):
        self.conn = conn
        self.llm = llm or LLM()
        # The adapter is trained only on island extraction + column mapping. Routing, entity resolution and
        # narrative facts use the base model: with the adapter, routing accuracy fell to 0 (task interference).
        self.base_llm = LLM(base_model=self.llm.base_model, adapter_path="", backend=self.llm.backend) if self.llm.adapter_path else self.llm
        self.use_llm = use_llm and self.llm.enabled
        self.force_llm_routing = force_llm_routing
        self.router = RouterAgent()
        self.validator = Validator(conn)
        self._side: dict[str, object] = {}   # run_id -> AgentResult / tracer (not JSON state)
        self.graph = self._build()

    # ------------------------------------------------------------------ graph
    def _build(self):
        g = StateGraph(PipelineState)
        g.add_node("intake", self.intake)
        g.add_node("route", self.route)
        g.add_node("extract", self.extract)
        g.add_node("validate", self.validate)
        g.add_node("load", self.load)
        g.add_node("finish", self.finish)
        g.add_edge(START, "intake")
        g.add_conditional_edges("intake", lambda s: "route" if s.get("current") else "finish", ["route", "finish"])
        g.add_conditional_edges("route", lambda s: "load" if s["agent_id"] == "skip" else "extract", ["load", "extract"])
        g.add_edge("extract", "validate")
        g.add_conditional_edges("validate", self._after_validate, ["extract", "load"])
        g.add_edge("load", "intake")
        g.add_edge("finish", END)
        return g.compile()

    def run(self, documents: list[dict], batch_id: str | None = None) -> dict:
        batch_id = batch_id or "B" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        state = {"batch_id": batch_id, "queue": list(documents), "done": [], "current": None}
        # each document visits ~6 nodes (+2 per retry)
        final = self.graph.invoke(state, {"recursion_limit": 20 + 12 * len(documents)})
        return {"batch_id": batch_id, "documents": final["done"]}

    # ------------------------------------------------------------------ nodes
    def intake(self, s: PipelineState) -> dict:
        if not s["queue"]:
            return {"current": None}
        doc, rest = s["queue"][0], s["queue"][1:]
        run_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO extraction_run (run_id,batch_id,document_id,agent_id,model_name,adapter,started_at,status) VALUES (?,?,?,?,?,?,?,?)",
            (run_id, s["batch_id"], doc["document_id"], "router_agent", None, None, now(), "running"))
        self.conn.commit()
        tracer = Tracer(run_id, "router_agent", doc["document_id"])
        self._side[run_id] = {"tracer": tracer}
        tracer.decision("intake", "rule", {"document": doc["document_id"], "file": doc["file_name"], "queue_left": len(rest)})
        return {"queue": rest, "current": doc, "run_id": run_id, "attempt": 1}

    def _ctx(self, s: PipelineState, attempt: int = 1, feedback: str = "") -> AgentContext:
        side = self._side[s["run_id"]]
        tracer = side["tracer"]
        doc = s["current"]
        if "norm" not in side:
            side["norm"] = Normalizer(self.conn, self.base_llm, tracer)
        return AgentContext(conn=self.conn, llm=self.llm, normalizer=side["norm"],
                            tracer=tracer, run_id=s["run_id"], batch_id=s["batch_id"], document=doc,
                            path=Path(doc["abs_path"]), attempt=attempt, feedback=feedback, use_llm=self.use_llm,
                            base_llm=self.base_llm)

    def route(self, s: PipelineState) -> dict:
        ctx = self._ctx(s)
        try:
            agent_id, by, reason = self.router.route(ctx, force_llm=self.force_llm_routing)
        except Exception as e:  # noqa: BLE001
            ctx.tracer.error("route", repr(e), handled_by="skip_document")
            agent_id, by, reason = "skip", "rule", f"router failure: {e}"
        self.conn.execute("UPDATE extraction_run SET agent_id=? WHERE run_id=?",
                          ("router_agent" if agent_id == "skip" else agent_id, s["run_id"]))
        return {"agent_id": agent_id, "routed_by": by}

    def extract(self, s: PipelineState) -> dict:
        attempt = s.get("attempt", 1)
        feedback = (s.get("validation") or {}).get("feedback", "") if attempt > 1 else ""
        ctx = self._ctx(s, attempt, feedback)
        agent = AGENTS[s["agent_id"]]()
        ctx.tracer.agent = agent.agent_id
        try:
            res = agent.run(ctx)
        except Exception as e:  # noqa: BLE001 - a crashing agent must not stop the batch
            ctx.tracer.error("agent_crash", f"{type(e).__name__}: {e}", handled_by="mark_failed")
            ctx.tracer.error("traceback", traceback.format_exc()[-1500:], handled_by="mark_failed")
            res = AgentResult(status="failed", notes=[f"{type(e).__name__}: {e}"])
        self._side[s["run_id"]]["result"] = res
        return {"result": {"status": res.status, "n": len(res.records), "facts": len(res.facts), "notes": res.notes[:10],
                           "unresolved": res.unresolved[:20], "stats": res.stats}}

    def validate(self, s: PipelineState) -> dict:
        side = self._side[s["run_id"]]
        res: AgentResult = side["result"]
        v = self.validator.validate(res.records, side["tracer"])
        side["validated"] = v
        summ = dict(v["summary"])
        summ["feedback"] = "; ".join(f"{e} x{n}" for e, n in summ["top_errors"])
        agent = AGENTS.get(s["agent_id"])
        attempt = s.get("attempt", 1)
        retry = (summ["error_rate"] > RETRY_ERROR_RATE and agent is not None and agent.uses_llm and self.use_llm
                 and attempt <= config.MAX_RETRIES)
        if retry:
            side["tracer"].decision("retry", "rule", {"attempt": attempt + 1, "error_rate": summ["error_rate"],
                                                      "feedback": summ["feedback"][:300]})
        return {"validation": summ, "retry": retry, "attempt": attempt + 1 if retry else attempt}

    @staticmethod
    def _after_validate(s: PipelineState) -> str:
        return "extract" if s.get("retry") else "load"

    def load(self, s: PipelineState) -> dict:
        side = self._side.pop(s["run_id"])
        tracer: Tracer = side["tracer"]
        doc = s["current"]
        if s["agent_id"] == "skip":
            status, n_loaded, n_rej, n_ext, notes = "skipped", 0, 0, 0, ["routed to skip"]
        else:
            res: AgentResult = side["result"]
            v = side["validated"]
            inserted, dup = insert_observations(self.conn, v["accepted"])
            for rec, err in v["rejected"]:
                insert_rejected(self.conn, s["run_id"], rec, err)
            nf = insert_text_facts(self.conn, res.facts)
            n_ext, n_loaded, n_rej, notes = len(res.records), inserted, len(v["rejected"]), res.notes
            if res.status == "failed":
                status = "failed"
            elif res.status == "partial" or res.unresolved:
                status = "partial"
            elif n_ext == 0 and not res.facts:
                status = "needs_review"
            else:
                status = "loaded"
            tracer.output("load", {"inserted": inserted, "duplicates_skipped": dup, "rejected": n_rej, "facts": nf, "status": status})
        if doc["abs_path"].lower().endswith(".pdf"):
            texts = [page_text_unicode(doc["abs_path"], i + 1) for i in range(len(page_texts(doc["abs_path"])))]
            upsert_chunks(self.conn, doc["document_id"], texts)
        trace_path = tracer.save()
        norm = side.get("norm")
        llm_calls = (norm.llm_calls if norm else 0) + sum(1 for st in tracer.steps if st["kind"] == "tool_call" and st["name"].startswith("llm_"))
        self.conn.execute(
            """UPDATE extraction_run SET finished_at=?, status=?, attempts=?, n_extracted=?, n_loaded=?, n_rejected=?,
                   n_llm_calls=?, model_name=?, adapter=?, trace_path=?, error=? WHERE run_id=?""",
            (now(), status, s.get("attempt", 1), n_ext, n_loaded, n_rej, llm_calls,
             self.llm.base_model if self.use_llm else None, self.llm.adapter_path if self.use_llm else None,
             str(Path(trace_path).relative_to(config.ROOT)), "; ".join(notes)[:1000] if notes else None, s["run_id"]))
        self.conn.commit()
        summary = {"document_id": doc["document_id"], "file": doc["file_name"], "run_id": s["run_id"], "agent": s["agent_id"],
                   "routed_by": s.get("routed_by"), "status": status, "attempts": s.get("attempt", 1), "extracted": n_ext,
                   "loaded": n_loaded, "rejected": n_rej, "llm_calls": llm_calls, "notes": notes[:5],
                   "validation": {k: v for k, v in (s.get("validation") or {}).items() if k != "feedback"}}
        return {"done": s["done"] + [summary], "current": None, "validation": {}, "result": {}}

    def finish(self, s: PipelineState) -> dict:
        return {}


# ---------------------------------------------------------------------- documents
def corpus_documents(conn, ids: list[str] | None = None) -> list[dict]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM document ORDER BY document_id")]
    if ids:
        rows = [r for r in rows if r["document_id"] in ids]
    for r in rows:
        r["abs_path"] = str(config.CORPUS_DIR / r["relative_path"])
    return rows


def register_unseen(conn, path: str) -> dict:
    """Register a file that is not in the manifest (e.g. an instructor document) as U## with no source group."""
    p = Path(path).resolve()
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    row = conn.execute("SELECT * FROM document WHERE sha256=?", (sha,)).fetchone()
    if row:
        d = dict(row)
        d["abs_path"] = str(p)
        return d
    n = conn.execute("SELECT COUNT(*) FROM document WHERE document_id LIKE 'U%'").fetchone()[0] + 1
    langs = {"languages": "unknown", "scripts": "", "legacy_font": False}
    pages = 1
    modality = "image"
    if p.suffix.lower() == ".pdf":
        texts = page_texts(str(p))
        pages = len(texts)
        langs = detect_languages(" ".join(texts))
        modality = "pdf_digital" if all(len(t.strip()) > 50 for t in texts) else "pdf_mixed"
    rec = {"doc_id": f"U{n:02d}", "source_id": "SRC_DES", "file_name": p.name, "relative_path": str(p),
           "document_url": "unseen document supplied at demo", "source_group": "G0_UNKNOWN", "period": _guess_period(p.name),
           "modality": modality, "languages": langs["languages"], "scripts": langs["scripts"],
           "legacy_font_encoding": langs["legacy_font"], "pages": pages, "sha256": sha,
           "collection_date": dt.date.today().isoformat(), "license": "unknown - supplied for evaluation"}
    upsert_document(conn, rec)
    conn.commit()
    d = dict(conn.execute("SELECT * FROM document WHERE document_id=?", (rec["doc_id"],)).fetchone())
    d["abs_path"] = str(p)
    return d


def _guess_period(name: str) -> str:
    import re
    m = re.search(r"(20\d{2})\s*[-–]\s*(\d{2,4})", name) or re.search(r"(20\d{2})", name)
    return m.group(0) if m else ""


_ = (json, guess_group)
