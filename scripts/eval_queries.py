"""Evaluate the Query Agent on the held-out query set (data/gold/queries.json).

Metrics per configuration: intent accuracy (Foundry "Intent Resolution"), tool-selection accuracy,
answer accuracy under the check rules in the gold file, citation groundedness (the cited page's text
contains the printed value), valid-plan rate, latency. Per query type and overall (macro over types).

  python scripts/eval_queries.py --label rules --planner rules
  python scripts/eval_queries.py --label base_zeroshot --planner model --zero-shot
  python scripts/eval_queries.py --label base_fewshot --planner model
  python scripts/eval_queries.py --label qlora_v1_fewshot --planner model --adapter adapters/34_AN_qlora_v1
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.query.agent import QueryAgent  # noqa: E402

TOOL_OF = {"rank": "rank_locations", "nearby": "nearby", "trend": "time_series", "provenance": "trace_value",
           "compare_sources": "compare_sources", "lookup": "trace_value"}
OUT = config.RESULTS_DIR / "phase3"


def close(a: float | None, lo: float, hi: float | None = None, tol: float = 0.005) -> bool:
    hi = lo if hi is None else hi
    return a is not None and lo * (1 - tol) - 1e-9 <= a <= hi * (1 + tol) + 1e-9


def check(item: dict, ans, gold: list[tuple]) -> tuple[bool, str]:
    rows, ck = ans.rows, item["check"]
    if not gold:
        return False, "empty gold"
    if not rows and ck != "agree":
        return False, "no rows"
    if ck == "top1":
        top_val = gold[0][1]
        tied = {g[0] for g in gold if abs(g[1] - top_val) < 1e-9}
        ok = rows[0].get("location_id") in tied and close(rows[0].get("value"), top_val)
        return ok, f"got {rows[0].get('location_id')}={rows[0].get('value')} want {sorted(tied)}={top_val}"
    if ck == "series":
        want = {g[0]: (g[1], g[2]) for g in gold}
        got = {r["period_label"]: r["value"] for r in rows}
        bad = [p for p in want if p not in got or not close(got[p], *want[p])]
        extra = [p for p in got if p not in want]
        return (not bad and not extra), f"missing/wrong {bad[:4]} extra {extra[:4]} ({len(got)}/{len(want)})"
    if ck == "peak":
        got = ans.summary.get("peak", (None,))[0]
        return got == gold[0][0], f"peak {got} want {gold[0][0]}"
    if ck == "provenance":
        c = ans.citations[0] if ans.citations else {}
        ok = any(c.get("document_id") == g[0] and c.get("page") == g[1] and close(rows[0].get("value"), g[2]) for g in gold)
        return ok, f"cited {c.get('document_id')} p{c.get('page')} value {rows[0].get('value')}"
    if ck == "value":
        vals = [g[2] for g in gold]
        return close(rows[0].get("value"), min(vals), max(vals)), f"got {rows[0].get('value')} want {min(vals)}..{max(vals)}"
    if ck == "agree":
        got = ans.summary.get("periods_with_2plus_sources")
        return got == gold[0][0], f"got {got} want {gold[0][0]}"
    return False, f"unknown check {ck}"


def grounded(conn, cite: dict) -> bool | None:
    """Is the printed value on the cited page? (None when the page text is not stored, e.g. OCR images)."""
    if not cite or cite.get("page") is None:
        return None
    r = conn.execute("SELECT text FROM document_chunk WHERE document_id=? AND page=?", (cite["document_id"], cite["page"])).fetchone()
    if not r or not r[0]:
        return None
    return str(cite.get("printed", "")).strip() in r[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--planner", choices=["rules", "model", "auto", "hybrid"], default="rules")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--zero-shot", action="store_true", help="model planner without the in-prompt examples")
    ap.add_argument("--only-demo", action="store_true")
    ap.add_argument("--set", choices=["dev", "test"], default="dev",
                    help="dev = queries.json (30, used while building the rule planner); test = queries_test.json (15, never used)")
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()

    llm = None
    if a.planner != "rules":
        from agri.llm.client import LLM
        llm = LLM(adapter_path=a.adapter)
    agent = QueryAgent(a.db, llm=llm, planner=a.planner, few_shot=not a.zero_shot)
    gold_conn = agent.conn
    gold_file = "queries.json" if a.set == "dev" else "queries_test.json"
    items = json.loads((config.ROOT / "data" / "gold" / gold_file).read_text())["queries"]
    if a.only_demo:
        items = [x for x in items if x["demo"]]
    results = []
    t0 = time.time()
    for it in items:
        gold = [tuple(r) for r in gold_conn.execute(it["gold_sql"]).fetchall()]
        ans = agent.ask(it["question"])
        ok, why = check(it, ans, gold)
        intent = ans.plan.get("intent") if ans.plan else None
        results.append({
            "id": it["id"], "type": it["type"], "lang": it["lang"], "demo": it["demo"], "question": it["question"],
            "planner_used": ans.planner, "valid_plan": bool(ans.plan), "intent_pred": intent, "intent_gold": it["intent"],
            "intent_ok": intent == it["intent"], "tool": ans.tool, "tool_ok": ans.tool == TOOL_OF[it["intent"]],
            "correct": ok, "detail": why, "grounded": grounded(gold_conn, ans.citations[0] if ans.citations else None),
            "latency_s": ans.latency_s, "answer": ans.text[:400], "plan": ans.plan, "error": ans.error})
        print(f"{it['id']:<4} {it['type']:<13} {'OK ' if ok else 'BAD'} intent={intent}  {why[:90]}", flush=True)

    def agg(rs: list[dict]) -> dict:
        g = [r["grounded"] for r in rs if r["grounded"] is not None]
        return {"n": len(rs), "answer_accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3),
                "intent_accuracy": round(sum(r["intent_ok"] for r in rs) / len(rs), 3),
                "tool_selection_accuracy": round(sum(r["tool_ok"] for r in rs) / len(rs), 3),
                "valid_plan_rate": round(sum(r["valid_plan"] for r in rs) / len(rs), 3),
                "citation_groundedness": round(sum(g) / len(g), 3) if g else None, "n_grounded_checked": len(g),
                "median_latency_s": round(statistics.median(r["latency_s"] for r in rs), 2)}
    by_type = {t: agg([r for r in results if r["type"] == t]) for t in sorted({r["type"] for r in results})}
    summary = {"label": a.label, "set": a.set, "planner": a.planner, "adapter": a.adapter, "few_shot": not a.zero_shot,
               "model": llm.label if llm else None, "overall": agg(results), "by_type": by_type,
               "macro_answer_accuracy": round(statistics.mean(v["answer_accuracy"] for v in by_type.values()), 3),
               "demo": agg([r for r in results if r["demo"]]) if any(r["demo"] for r in results) else None,
               "hindi": agg([r for r in results if r["lang"] == "hi"]) if any(r["lang"] == "hi" for r in results) else None,
               "elapsed_s": round(time.time() - t0, 1), "results": results}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"query_eval_{a.set}_{a.label}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    o = summary["overall"]
    print(f"\n{a.label}: answer {o['answer_accuracy']} (n={o['n']}), macro {summary['macro_answer_accuracy']}, "
          f"intent {o['intent_accuracy']}, tool {o['tool_selection_accuracy']}, valid plans {o['valid_plan_rate']}, "
          f"grounded {o['citation_groundedness']} (n={o['n_grounded_checked']}) -> {path}")


if __name__ == "__main__":
    main()
