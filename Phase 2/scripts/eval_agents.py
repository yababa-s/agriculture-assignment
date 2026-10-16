"""Agent / workflow evaluation of one pipeline batch (Foundry agent-evaluator menu + direct checks).

Evaluators used (Foundry name -> our implementation):
  Tool Call Accuracy / tool selection -> router decision vs data/gold/routing.json
  Tool Call Accuracy / trajectory     -> AgentEvals trajectory match (superset) vs reference tool sequences
  Tool Input Accuracy                 -> per-tool argument validators on every recorded tool call
  Tool Output Utilization             -> tool results that led to records (non-empty extraction after the call)
  Task Completion                     -> terminal status per document (loaded=1, partial=0.5, other=0)
  Task Adherence                      -> validator acceptance rate (schema, ranges, units) per agent
  Groundedness                        -> every loaded value_raw found verbatim on its cited page (text layer)
  Task Navigation Efficiency          -> LLM calls, retries, duplicate rows, rejected model outputs per document
  + direct value checks               -> data/gold/value_checks.json (values read by eye from rendered pages)
Skipped (and why) is written into the report: Intent Resolution, Relevance, Coherence, Fluency,
Response Completeness (Phase 2 produces records, not natural-language answers; planned for the Phase 3
query agent), content-safety evaluators (no user-facing generated text; inputs are government statistics).

Usage: python scripts/eval_agents.py [--batch BATCH_ID]   (default: latest batch in the DB)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentevals.trajectory.match import create_trajectory_match_evaluator  # noqa: E402

from agri import config  # noqa: E402
from agri.db.db import connect  # noqa: E402
from agri.tools.pdf_tools import page_texts  # noqa: E402

REFERENCE_TOOLS = {  # minimal tool sequence each agent must call to do its job
    "matrix_table_agent": ["pdf_extract_tables"],
    "bilingual_table_agent": ["pdf_extract_tables"],
    "price_table_agent": ["pdf_extract_tables"],
    "lulc_agent": ["pdf_extract_tables"],
    "island_profile_agent": ["select_relevant_lines"],
    "narrative_agent": ["segment_schemes"],
    "image_table_agent": ["ocr_image"],
}
LLM_REFERENCE = {"island_profile_agent": ["select_relevant_lines", "llm_extract_profile"],
                 "narrative_agent": ["segment_schemes", "llm_extract_facts"]}
GROUP_OF = {"matrix_table_agent": "G1", "bilingual_table_agent": "G2", "price_table_agent": "G3",
            "island_profile_agent": "G4", "narrative_agent": "G5", "image_table_agent": "G6", "lulc_agent": "G7",
            "router_agent": "G8/skip"}
SKIPPED = {
    "Intent Resolution": "no user intent in Phase 2 (batch extraction); evaluated in Phase 3 query agent",
    "Relevance / Coherence / Fluency / Response Completeness": "agents emit structured records, not prose answers",
    "Content safety (violence, self-harm, hate, sexual), Protected material": "inputs are public statistics; no generated user-facing text",
    "Code vulnerability / Ungrounded attributes": "no generated code; no person-level attributes are extracted (no PII by design)",
}


def load_trace(path: str) -> list[dict]:
    p = config.ROOT / path
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def to_messages(steps: list[dict]) -> list[dict]:
    msgs = [{"role": "user", "content": "extract"}]
    for s in steps:
        if s["kind"] == "tool_call":
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": s["name"], "arguments": "{}"}}]})
        elif s["kind"] == "tool_result":
            msgs.append({"role": "tool", "content": "ok"})
    msgs.append({"role": "assistant", "content": "done"})
    return msgs


def ref_messages(tools: list[str]) -> list[dict]:
    msgs = [{"role": "user", "content": "extract"}]
    for t in tools:
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": t, "arguments": "{}"}}]})
    msgs.append({"role": "assistant", "content": "done"})
    return msgs


def tool_input_ok(step: dict, doc_path: str) -> bool:
    a = step["payload"] or {}
    n = step["name"]
    if n in ("pdf_extract_tables", "ocr_image", "fingerprint_document"):
        return Path(str(a.get("path", ""))).resolve() == Path(doc_path).resolve()
    if n == "llm_map_columns":
        return isinstance(a.get("columns"), list) and len(a["columns"]) > 0 and bool(a.get("table"))
    if n == "select_relevant_lines":
        return bool(a.get("block"))
    if n == "llm_extract_profile":
        return str(a.get("island", "")).startswith("ISL_")
    if n == "llm_resolve_entity":
        return bool(a.get("label")) and len(a.get("candidates") or []) > 0
    if n in ("segment_schemes", "read_outlay_block", "llm_extract_facts", "llm_route"):
        return True
    return True


_WS = re.compile(r"\s+")


def grounded(conn, batch_id: str) -> dict:
    """value_raw of every loaded numeric observation must occur on its cited page."""
    res = defaultdict(lambda: {"checked": 0, "found": 0})
    q = """SELECT o.agent_id, o.document_id, o.page, o.value_raw, d.relative_path, d.modality
           FROM observation o JOIN extraction_run r ON r.run_id=o.run_id JOIN document d ON d.document_id=o.document_id
           WHERE r.run_id IN (SELECT value FROM json_each(?)) AND o.value IS NOT NULL AND o.value_raw <> ''"""
    cache = {}
    for agent, doc, page, raw, rel, modality in conn.execute(q, (batch_id,)):  # batch_id here is a JSON list of run ids
        if not str(rel).lower().endswith(".pdf"):
            continue
        path = str(config.CORPUS_DIR / rel) if not Path(rel).is_absolute() else rel
        key = (path, page)
        if key not in cache:
            cache[key] = _WS.sub("", page_texts(path)[page - 1]) if page else ""
        res[agent]["checked"] += 1
        res[agent]["found"] += _WS.sub("", raw) in cache[key]
    return {a: {**v, "rate": round(v["found"] / max(1, v["checked"]), 4)} for a, v in res.items()}


def value_checks(conn) -> dict:
    checks = json.loads((config.GOLD_DIR / "value_checks.json").read_text())["checks"]
    ok, rows = 0, []
    for c in checks:
        sql = ("SELECT value, unit_id, dims FROM observation WHERE document_id=? AND metric_id=? AND location_id=? "
               "AND period_label=? AND " + ("commodity_id=?" if c.get("commodity") else "commodity_id IS NULL"))
        params = [c["doc"], c["metric"], c["location"], c["period"]] + ([c["commodity"]] if c.get("commodity") else [])
        cands = conn.execute(sql, params).fetchall()
        if c.get("dims"):
            cands = [r for r in cands if all(json.loads(r["dims"]).get(k) == v for k, v in c["dims"].items())]
        hit = any(r["value"] is not None and abs(r["value"] - c["value"]) < 1e-6 and (not c.get("unit") or r["unit_id"] == c["unit"])
                  for r in cands)
        ok += hit
        rows.append({**c, "found": [r["value"] for r in cands][:3], "ok": hit})
    return {"n": len(checks), "correct": ok, "accuracy": round(ok / len(checks), 4),
            "failures": [r for r in rows if not r["ok"]]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default=None)
    a = ap.parse_args()
    conn = connect(config.DB_PATH)
    batch = a.batch or conn.execute("SELECT batch_id FROM extraction_run ORDER BY started_at DESC LIMIT 1").fetchone()[0]
    # latest run of every document at or before the chosen batch (so a targeted re-run replaces only its documents)
    runs = [dict(r) for r in conn.execute(
        "SELECT r.*, d.relative_path, d.source_group, d.file_name FROM extraction_run r JOIN document d USING(document_id) "
        "WHERE r.batch_id <= ? AND r.started_at = (SELECT MAX(started_at) FROM extraction_run x "
        "WHERE x.document_id = r.document_id AND x.batch_id <= ?) AND r.document_id LIKE 'D%' ORDER BY document_id", (batch, batch))]
    routing_gold = {g["document_id"]: g["expected_agent"] for g in json.loads((config.GOLD_DIR / "routing.json").read_text())}
    superset = create_trajectory_match_evaluator(trajectory_match_mode="superset")

    per_doc, per_agent = [], defaultdict(lambda: defaultdict(float))
    for r in runs:
        steps = load_trace(r["trace_path"]) if r["trace_path"] else []
        doc_path = r["relative_path"] if Path(r["relative_path"]).is_absolute() else str(config.CORPUS_DIR / r["relative_path"])
        routed = next((s["payload"].get("agent") for s in steps if s["kind"] == "decision" and s["name"] == "route"), None)
        routed_by = next((s["by"] for s in steps if s["kind"] == "decision" and s["name"] == "route"), None)
        agent = routed or r["agent_id"]
        calls = [s for s in steps if s["kind"] == "tool_call"]
        results = [s for s in steps if s["kind"] == "tool_result"]
        ref = LLM_REFERENCE.get(agent) if (r["model_name"] and agent in LLM_REFERENCE) else REFERENCE_TOOLS.get(agent)
        traj = superset(outputs=to_messages(steps), reference_outputs=ref_messages(ref))["score"] if ref else None
        inputs_ok = sum(tool_input_ok(s, doc_path) for s in calls)
        completion = {"loaded": 1.0, "partial": 0.5}.get(r["status"], 1.0 if r["status"] == "skipped" and agent == "skip" else 0.0)
        model_rejects = sum(len(s["payload"].get("rejected", [])) for s in steps if s["kind"] == "decision" and s["by"] == "model"
                            and isinstance(s["payload"], dict) and isinstance(s["payload"].get("rejected"), list))
        errors_handled = [{"error": s["name"], "handled_by": s["payload"].get("handled_by")} for s in steps if s["kind"] == "error"]
        d = {"document_id": r["document_id"], "file": r["file_name"], "agent": agent, "group": GROUP_OF.get(agent, "?"),
             "routed_by": routed_by, "routing_correct": agent == routing_gold.get(r["document_id"], agent),
             "status": r["status"], "task_completion": completion, "trajectory_superset_match": traj,
             "tool_calls": len(calls), "tool_input_accuracy": round(inputs_ok / max(1, len(calls)), 3) if calls else None,
             "tool_results_ok": sum(1 for s in results if s["payload"].get("ok")), "n_extracted": r["n_extracted"],
             "n_loaded": r["n_loaded"], "n_rejected": r["n_rejected"],
             "task_adherence": round(r["n_loaded"] / max(1, r["n_loaded"] + r["n_rejected"]), 4) if r["n_extracted"] else None,
             "llm_calls": r["n_llm_calls"], "attempts": r["attempts"], "model_outputs_rejected": model_rejects,
             "manual_interventions": r["manual_interventions"], "errors_handled": errors_handled[:8],
             "duplicates_skipped": max(0, (r["n_extracted"] or 0) - (r["n_loaded"] or 0) - (r["n_rejected"] or 0))}
        per_doc.append(d)
        pa = per_agent[agent]
        pa["documents"] += 1
        for k in ("task_completion", "n_loaded", "n_rejected", "llm_calls", "model_outputs_rejected", "tool_calls"):
            pa[k] += d[k] or 0
        pa["routing_correct"] += d["routing_correct"]
        pa["trajectory_ok"] += bool(traj)
    for agent, pa in per_agent.items():
        n = pa["documents"]
        pa["task_completion"] = round(pa["task_completion"] / n, 3)
        pa["routing_accuracy"] = round(pa.pop("routing_correct") / n, 3)
        ok = pa.pop("trajectory_ok")
        pa["trajectory_match_rate"] = round(ok / n, 3) if agent in REFERENCE_TOOLS else None
        pa["task_adherence"] = round(pa["n_loaded"] / (pa["n_loaded"] + pa["n_rejected"]), 4) if pa["n_loaded"] + pa["n_rejected"] else None

    g = grounded(conn, json.dumps([r["run_id"] for r in runs]))
    vc = value_checks(conn)
    attempted = len(runs)
    auto_done = sum(1 for d in per_doc if d["status"] in ("loaded", "partial", "skipped") and d["manual_interventions"] == 0)
    workflow = {
        "documents": attempted, "routing_accuracy": round(sum(d["routing_correct"] for d in per_doc) / attempted, 3),
        "task_completion_mean": round(sum(d["task_completion"] for d in per_doc) / attempted, 3),
        "observations_loaded": sum(d["n_loaded"] for d in per_doc), "rejected": sum(d["n_rejected"] for d in per_doc),
        "groundedness_overall": round(sum(v["found"] for v in g.values()) / max(1, sum(v["checked"] for v in g.values())), 4),
        "value_check_accuracy": vc["accuracy"],
        "automation": {
            "inputs_completed_without_manual_intervention": auto_done, "inputs_attempted": attempted,
            "automation_rate": round(auto_done / attempted, 3),
            "manual_interventions_in_run": sum(d["manual_interventions"] for d in per_doc),
            "retries": sum(d["attempts"] - 1 for d in per_doc), "llm_calls": sum(d["llm_calls"] for d in per_doc),
            "model_outputs_rejected_by_gates": sum(d["model_outputs_rejected"] for d in per_doc),
            "duplicate_rows_skipped": sum(d["duplicates_skipped"] for d in per_doc),
            "needs_review_or_failed": [d["document_id"] for d in per_doc if d["status"] in ("needs_review", "failed")],
        },
    }
    out = {"batch_id": batch, "workflow": workflow, "per_agent": per_agent, "per_document": per_doc,
           "groundedness_by_agent": g, "value_checks": vc, "evaluators_skipped": SKIPPED}
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RESULTS_DIR / f"agent_eval_{batch}.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(workflow, indent=2))
    print(f"{'agent':<24}{'docs':>5}{'compl':>7}{'traj':>6}{'adher':>8}{'loaded':>8}{'llm':>6}{'rej_out':>8}")
    for a_, pa in sorted(per_agent.items()):
        print(f"{a_:<24}{int(pa['documents']):>5}{pa['task_completion']:>7}{str(pa['trajectory_match_rate']):>6}{str(pa['task_adherence']):>8}"
              f"{int(pa['n_loaded']):>8}{int(pa['llm_calls']):>6}{int(pa['model_outputs_rejected']):>8}")
    print("groundedness:", {k: v["rate"] for k, v in g.items()})
    print("value checks:", vc["correct"], "/", vc["n"], [(f["doc"], f["metric"], f.get("commodity"), f["value"], f["found"]) for f in vc["failures"]][:8])
    print(f"-> {path}")


if __name__ == "__main__":
    main()
