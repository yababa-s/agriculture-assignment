"""Push the held-out gold sets to LangSmith and record base vs LoRA experiments there.

Needs LANGSMITH_API_KEY (free tier is enough). Without it the script explains what to do and exits;
all the same numbers are produced locally by scripts/eval_llm_tasks.py.

  export LANGSMITH_API_KEY=...            # https://smith.langchain.com -> Settings -> API keys
  python scripts/langsmith_eval.py --adapter adapters/TEAMID_AN_qlora_v1

Datasets created: <project>-island-D10, <project>-columns-eval, <project>-routing
Experiments: one per model (base, adapter), each scored by the evaluators below. Pipeline runs are
already traced to the LangSmith project when the key is set (agri/config.py enables tracing).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.agents.island_agent import SYSTEM as ISLAND_SYSTEM, build_prompt, check_item  # noqa: E402
from agri.llm.client import LLM  # noqa: E402
from agri.tools.parsing import parse_period  # noqa: E402


def _num(v):
    try:
        return round(float(str(v).replace(",", "")), 6)
    except (TypeError, ValueError):
        return None


def island_f1(run, example) -> dict:
    gold = {(i["metric"], i.get("qualifier"), _num(i["value"])) for i in example.outputs["items"]}
    pred = {(i.get("metric"), i.get("qualifier") or None, _num(i.get("value"))) for i in run.outputs.get("items", []) if isinstance(i, dict)}
    tp = len(gold & pred)
    p, r = tp / max(1, len(pred)), tp / max(1, len(gold))
    return {"key": "item_f1", "score": 2 * p * r / max(1e-9, p + r)}


def island_grounded(run, example) -> dict:
    items = [i for i in run.outputs.get("items", []) if isinstance(i, dict)]
    ok = sum(check_item(i, example.inputs["input"]) is None for i in items)
    return {"key": "groundedness", "score": ok / max(1, len(items))}


def column_acc(run, example) -> dict:
    pred = {i.get("col"): i for i in run.outputs.get("items", []) if isinstance(i, dict)}
    n = ok = 0
    for g in example.outputs["answer"]:
        n += 1
        p = pred.get(g["col"], {})
        per = parse_period(str(p.get("period") or ""))
        ok += p.get("location") == g["location"] and p.get("metric") == g["metric"] and bool(per) and per["period_label"] == g["period"]
    return {"key": "column_accuracy", "score": ok / max(1, n)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=None)
    a = ap.parse_args()
    if not os.getenv("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY is not set. Create a free key at https://smith.langchain.com (Settings > API Keys),\n"
              "then: export LANGSMITH_API_KEY=... && python scripts/langsmith_eval.py --adapter adapters/TEAMID_AN_qlora_v1")
        return
    from langsmith import Client
    client = Client()
    proj = config.LANGSMITH_PROJECT
    isl = json.loads((config.GOLD_DIR / "island_profiles_D10.json").read_text())["blocks"]
    cols = json.loads((config.GOLD_DIR / "column_mapping_eval.json").read_text())["examples"]

    def dataset(name, inputs, outputs):
        if client.has_dataset(dataset_name=name):
            return name
        ds = client.create_dataset(name, description="held-out gold from eval documents only")
        client.create_examples(inputs=inputs, outputs=outputs, dataset_id=ds.id)
        return name

    d_isl = dataset(f"{proj}-island-D10", [{"input": b["input"], "island": b["island"]} for b in isl], [{"items": b["items"]} for b in isl])
    d_col = dataset(f"{proj}-columns-eval", [{"system": e["system"], "user": e["user"]} for e in cols], [{"answer": e["answer"]} for e in cols])

    for label, adapter in [("base", None), ("qlora", a.adapter)]:
        if label == "qlora" and not adapter:
            continue
        llm = LLM(adapter_path=adapter)

        def island_target(inputs: dict) -> dict:
            r = llm.json_call(ISLAND_SYSTEM, build_prompt(inputs["input"]), max_tokens=2000)
            return {"items": r.parsed if isinstance(r.parsed, list) else [], "raw": r.text}

        def column_target(inputs: dict) -> dict:
            r = llm.json_call(inputs["system"], inputs["user"], max_tokens=600)
            return {"items": r.parsed if isinstance(r.parsed, list) else [], "raw": r.text}

        client.evaluate(island_target, data=d_isl, evaluators=[island_f1, island_grounded], experiment_prefix=f"island-{label}",
                        metadata={"model": llm.label}, max_concurrency=1)
        client.evaluate(column_target, data=d_col, evaluators=[column_acc], experiment_prefix=f"columns-{label}",
                        metadata={"model": llm.label}, max_concurrency=1)
    print(f"Experiments recorded in LangSmith project datasets {d_isl}, {d_col}")


if __name__ == "__main__":
    main()
