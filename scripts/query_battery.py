"""Run the coverage battery (data/gold/queries_battery.json) through the Query Agent and check each plan.

A question passes when (a) the plan matches every expected field (intent, metric, item, place, level, order),
(b) an answerable question returns rows (no "No data" / failure), and (c) an off-topic question is refused.
Writes eval/results/phase3/query_battery_{label}.json and prints the failures.

  python scripts/query_battery.py                       # rules planner
  python scripts/query_battery.py --planner hybrid --adapter adapters/34_AN_qlora_v2 --label hybrid
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402
from agri.query.agent import QueryAgent  # noqa: E402

FIELD = {"intent": "intent", "metric": "metric", "commodity": "commodity", "location": "location", "level": "level",
         "order": "order"}


def judge(item: dict, ans) -> tuple[bool, str]:
    exp = item["expect"]
    if exp.get("refuse"):
        return ans.query_type == "out_of_scope", f"not refused: {ans.text[:80]}"
    if ans.query_type in ("out_of_scope", "unknown"):
        return False, f"refused/failed: {ans.text[:100]}"
    plan = ans.plan or {}
    bad = [f"{k}={plan.get(FIELD[k])!r} want {v!r}" for k, v in exp.items() if k in FIELD and plan.get(FIELD[k]) != v]
    if bad:
        return False, "; ".join(bad)
    if exp.get("no_data"):          # the knowledge base has no such figure: the answer must say so, not invent one
        return (not ans.rows and ans.text.startswith("No data")), f"expected a 'No data' answer: {ans.text[:80]}"
    if not ans.rows:
        return False, f"no rows: {ans.text[:100]}"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", default="rules")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--label", default="rules")
    a = ap.parse_args()
    llm = None
    if a.planner != "rules":
        from agri.llm.client import LLM
        llm = LLM(adapter_path=a.adapter)
    agent = QueryAgent(planner=a.planner, llm=llm, few_shot=False)
    items = json.loads((config.ROOT / "data/gold/queries_battery.json").read_text(encoding="utf-8"))["queries"]
    out, fails = [], Counter()
    for it in items:
        ans = agent.ask(it["q"])
        ok, why = judge(it, ans)
        out.append({"q": it["q"], "ok": ok, "why": why, "plan": ans.plan, "planner": ans.planner,
                    "answer": ans.text[:400]})
        if not ok:
            fails[why.split(":")[0].split("=")[0]] += 1
            print(f"FAIL  {it['q']!r}\n      {why}")
    n_ok = sum(o["ok"] for o in out)
    print(f"\n{n_ok}/{len(out)} pass ({100 * n_ok / len(out):.1f}%)  failure kinds: {dict(fails)}")
    path = config.RESULTS_DIR / "phase3" / f"query_battery_{a.label}.json"
    path.write_text(json.dumps({"n": len(out), "n_pass": n_ok, "items": out}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("->", path)


if __name__ == "__main__":
    main()
