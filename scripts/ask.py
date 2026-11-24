"""Ask the knowledge base a question in English or Hindi. Every answer cites document, page and cell.

  python scripts/ask.py "Which agri zone produced the most paddy in 2025-26?"
  python scripts/ask.py "Which source and page did the 2025-26 coconut production figure come from?" --show-source
  python scripts/ask.py --no-llm "..."            # rule planner only (any OS, no model)
  python scripts/ask.py --adapter adapters/34_AN_qlora_v2 "..."
  python scripts/ask.py --explain "..."           # print plan, tool and SQL
  python scripts/ask.py --demo                    # run the 10 demo queries (data/gold/demo_queries.json)
  python scripts/ask.py                           # interactive prompt
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.query.agent import QueryAgent  # noqa: E402


def open_file(path: str) -> None:
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", path], check=False)
        elif platform.system() == "Windows":
            import os
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        else:
            subprocess.run(["xdg-open", path], check=False, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def show(agent: QueryAgent, q: str, a) -> None:
    ans = agent.ask(q)
    print(f"\nQ: {q}\n[{ans.query_type} | planner={ans.planner} | tool={ans.tool} | {ans.latency_s}s | id={ans.query_id}]")
    print(ans.text)
    if a.explain:
        print("\nplan:", json.dumps(ans.plan, ensure_ascii=False))
        print("tool args:", json.dumps(ans.args, ensure_ascii=False, default=str))
        print("SQL:\n" + ans.sql)
    if a.json:
        print(ans.to_json())
    if a.show_source and ans.citations and ans.citations[0].get("obs_id"):
        from agri.query.provenance import render_source
        info = render_source(agent.conn, ans.citations[0]["obs_id"])
        print(f"\nsource page: {info['image']}  (cell highlighted: {info['highlighted']})")
        if not a.no_open:
            open_file(info["image"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="*")
    ap.add_argument("--no-llm", action="store_true", help="rule planner only")
    ap.add_argument("--adapter", default=None, help="LoRA adapter directory for the planner model")
    ap.add_argument("--planner", choices=["hybrid", "auto", "model", "rules"], default="hybrid")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-source", action="store_true", help="render the cited page with the cell highlighted")
    ap.add_argument("--no-open", action="store_true", help="with --show-source: save the image without opening it")
    ap.add_argument("--demo", action="store_true", help="run the 10 demo queries")
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()

    llm = None
    if not a.no_llm and a.planner != "rules" and config.LLM_BACKEND != "none":
        from agri.llm.client import LLM
        llm = LLM(adapter_path=a.adapter or config.QUERY_ADAPTER_PATH)
    try:
        agent = QueryAgent(a.db, llm=llm, planner="rules" if llm is None else a.planner, few_shot=False)
    except FileNotFoundError as e:   # no database yet: print the fix, not a traceback
        sys.exit(f"FileNotFoundError: {e}")
    if a.demo:
        demo = json.loads((config.ROOT / "data" / "gold" / "demo_queries.json").read_text(encoding="utf-8"))
        for d in demo:
            show(agent, d["question"], a)
        return
    if a.question:
        show(agent, " ".join(a.question), a)
        return
    print("Ask a question (blank line to quit).")
    while True:
        try:
            q = input("\n? ").strip()
        except EOFError:
            break
        if not q:
            break
        show(agent, q, a)


if __name__ == "__main__":
    main()
