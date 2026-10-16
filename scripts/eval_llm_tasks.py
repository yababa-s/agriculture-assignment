"""Evaluate the LLM on held-out tasks, with and without the LoRA adapter.

Tasks (all inputs come from EVAL documents only; see data/splits/splits.json):
  island   : island-profile extraction on D10 (31 islands, 294 reference items)
  columns  : column mapping on D02 + D06 tables (74 reference columns)
  routing  : agent selection for all 20 corpus files from fingerprint + first page (no manifest)

Model output is scored raw (no teacher fill, no retries) so the number reflects the model.
Usage: python scripts/eval_llm_tasks.py --label base
       python scripts/eval_llm_tasks.py --label qlora_v1 --adapter adapters/TEAMID_AN_qlora_v1
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
import re  # noqa: E402

from agri.agents.island_agent import CATALOGUE, SYSTEM as ISLAND_SYSTEM, build_prompt, check_item, teacher_extract  # noqa: E402
from agri.agents.router import AGENT_GUIDE, SYSTEM as ROUTER_SYSTEM, fingerprint, heuristic_route, router_prompt  # noqa: E402
from agri.llm.client import LLM  # noqa: E402
from agri.tools.parsing import parse_period  # noqa: E402


def _num(v):
    try:
        return round(float(str(v).replace(",", "")), 6)
    except (TypeError, ValueError):
        return None


_KV = re.compile(r"(?<![\w(])([A-Z][A-Za-z /&.]{2,40}?)\s*[-–]\s*(\d[\d,]*(?:\.\d+)?)")


def perturb(text: str) -> str:
    """Unseen layout: 'Farmers-6192 Agricultural Depot-13' -> '6192 farmers; 13 agricultural depot'.
    Same facts, different surface form; header lines with areas and census figures are left alone."""
    out = []
    for line in text.splitlines():
        if line.startswith(("Area", "Population")) or not _KV.search(line):
            out.append(line)
            continue
        out.append(_KV.sub(lambda m: f"{m.group(2)} {m.group(1).strip().lower()};", line))
    return "\n".join(out)


def eval_island(llm: LLM | None, limit: int | None, perturbed: bool = False) -> dict:
    """llm=None scores the deterministic teacher extractor instead of a model."""
    gold = json.loads((config.GOLD_DIR / "island_profiles_D10.json").read_text())["blocks"]
    if limit:
        gold = gold[:limit]
    if perturbed:
        gold = [{**b, "input": perturb(b["input"])} for b in gold]
    tp = fp = fn = 0
    tp_g = fp_g = 0
    json_ok = in_cat = grounded = n_pred = 0
    per_metric = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
    lat, examples = [], []
    salvaged = 0
    for b in gold:
        gset = {(i["metric"], i.get("qualifier"), _num(i["value"])) for i in b["items"]}
        if llm is None:
            t0 = time.time()
            preds = [{k: x[k] for k in ("metric", "value", "unit", "qualifier", "evidence")} for x in teacher_extract(b["input"])]
            lat.append(time.time() - t0)
            json_ok += 1
        else:
            r = llm.json_call(ISLAND_SYSTEM, build_prompt(b["input"]), max_tokens=2000)
            lat.append(r.latency_s)
            preds = r.parsed if r.ok and isinstance(r.parsed, list) else []
            json_ok += 1 if (r.ok and isinstance(r.parsed, list) and not r.salvaged) else 0
            salvaged += 1 if r.salvaged else 0
        pset, pset_g = set(), set()
        for it in preds:
            if not isinstance(it, dict):
                continue
            n_pred += 1
            key = (it.get("metric"), it.get("qualifier") or None, _num(it.get("value")))
            pset.add(key)
            if it.get("metric") in CATALOGUE:
                in_cat += 1
            if check_item(it, b["input"]) is None:
                grounded += 1
                pset_g.add(key)
        tp += len(gset & pset); fp += len(pset - gset); fn += len(gset - pset)
        tp_g += len(gset & pset_g); fp_g += len(pset_g - gset)
        for k in gset:
            per_metric[k[0]]["tp" if k in pset else "fn"] += 1
        for k in pset - gset:
            per_metric[str(k[0])]["fp"] += 1
        if len(examples) < 3:
            examples.append({"island": b["island"], "missed": sorted(map(str, gset - pset))[:6],
                             "spurious": sorted(map(str, pset - gset))[:6]})
    prf = lambda t, f_p, f_n: (t / max(1, t + f_p), t / max(1, t + f_n))  # noqa: E731
    p, rc = prf(tp, fp, fn)
    pg, rg = prf(tp_g, fp_g, fn + (tp - tp_g))
    f1 = lambda a, b: 2 * a * b / max(1e-9, a + b)  # noqa: E731
    return {
        "n_islands": len(gold), "n_gold_items": tp + fn, "n_pred_items": n_pred,
        "json_valid_rate": round(json_ok / len(gold), 3),
        "json_salvaged_rate": round(salvaged / len(gold), 3),
        "catalogue_adherence": round(in_cat / max(1, n_pred), 3),
        "groundedness_rate": round(grounded / max(1, n_pred), 3),
        "raw": {"precision": round(p, 3), "recall": round(rc, 3), "f1": round(f1(p, rc), 3)},
        "after_groundedness_gate": {"precision": round(pg, 3), "recall": round(rg, 3), "f1": round(f1(pg, rg), 3)},
        "per_metric_recall": {m: round(v["tp"] / max(1, v["tp"] + v["fn"]), 2) for m, v in sorted(per_metric.items()) if v["tp"] + v["fn"]},
        "latency_s_median": round(statistics.median(lat), 2), "examples": examples,
    }


def eval_columns(llm: LLM, limit: int | None) -> dict:
    gold = json.loads((config.GOLD_DIR / "column_mapping_eval.json").read_text())["examples"]
    if limit:
        gold = gold[:limit]
    n = full = loc = met = per = 0
    json_ok = 0
    lat, errors = [], []
    for ex in gold:
        r = llm.json_call(ex["system"], ex["user"], max_tokens=60 * len(ex["answer"]) + 80)
        lat.append(r.latency_s)
        pred = {}
        if r.ok and isinstance(r.parsed, list):
            json_ok += 1
            pred = {it.get("col"): it for it in r.parsed if isinstance(it, dict)}
        for g in ex["answer"]:
            n += 1
            p = pred.get(g["col"], {})
            pp = parse_period(str(p.get("period") or ""))
            ok_l = p.get("location") == g["location"]
            ok_m = p.get("metric") == g["metric"]
            ok_p = bool(pp) and pp["period_label"] == g["period"]
            loc += ok_l; met += ok_m; per += ok_p; full += ok_l and ok_m and ok_p
            if not (ok_l and ok_m and ok_p) and len(errors) < 6:
                errors.append({"doc": ex["document_id"], "table": ex["table"], "col": g["col"], "gold": [g["location"], g["metric"], g["period"]],
                               "pred": [p.get("location"), p.get("metric"), p.get("period")]})
    return {"n_examples": len(gold), "n_columns": n, "json_valid_rate": round(json_ok / max(1, len(gold)), 3),
            "column_accuracy": round(full / max(1, n), 3), "location_accuracy": round(loc / max(1, n), 3),
            "metric_accuracy": round(met / max(1, n), 3), "period_accuracy": round(per / max(1, n), 3),
            "latency_s_median": round(statistics.median(lat), 2), "errors": errors}


def eval_routing(llm: LLM) -> dict:
    gold = json.loads((config.GOLD_DIR / "routing.json").read_text())
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH)
    paths = {r[0]: str(config.CORPUS_DIR / r[1]) for r in conn.execute("SELECT document_id, relative_path FROM document")}
    cache = config.RESULTS_DIR / "fingerprints.json"
    fps = json.loads(cache.read_text()) if cache.exists() else {}
    correct, rows = 0, []
    for g in gold:
        fp = fps.get(g["document_id"]) or fingerprint(paths[g["document_id"]])
        fps[g["document_id"]] = fp
        r = llm.json_call(ROUTER_SYSTEM, router_prompt(fp), max_tokens=80)
        agent = r.parsed.get("agent") if r.ok and isinstance(r.parsed, dict) else None
        ok = agent == g["expected_agent"]
        correct += ok
        h, confident = heuristic_route(fp)
        hybrid = h if confident or agent not in AGENT_GUIDE else agent
        rows.append({"doc": g["document_id"], "expected": g["expected_agent"], "predicted": agent,
                     "valid_id": agent in AGENT_GUIDE, "ok": ok, "heuristic_confident": confident,
                     "hybrid": hybrid, "hybrid_ok": hybrid == g["expected_agent"]})
    cache.write_text(json.dumps(fps, indent=1, default=str))
    amb = [r for r in rows if not r["heuristic_confident"]]
    return {"n": len(gold), "accuracy": round(correct / len(gold), 3),
            "valid_agent_id_rate": round(sum(r["valid_id"] for r in rows) / len(rows), 3),
            "hybrid_accuracy": round(sum(r["hybrid_ok"] for r in rows) / len(rows), 3),
            "model_accuracy_on_ambiguous": round(sum(r["ok"] for r in amb) / max(1, len(amb)), 3),
            "n_ambiguous": len(amb), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--tasks", default="island,columns,routing")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    llm = None if a.label == "teacher" else LLM(adapter_path=a.adapter)
    out = {"label": a.label, "model": llm.label if llm else "rule teacher (regex)", "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    t0 = time.time()
    if "perturbed" in a.tasks:
        out["island_perturbed"] = eval_island(llm, a.limit, perturbed=True)
        print("island_perturbed", {k: v for k, v in out["island_perturbed"].items() if k not in ("per_metric_recall", "examples")})
    if "island" in a.tasks.replace("island_perturbed", ""):
        out["island_extraction"] = eval_island(llm, a.limit)
        print("island", {k: v for k, v in out["island_extraction"].items() if k not in ("per_metric_recall", "examples")})
    if "columns" in a.tasks:
        out["column_mapping"] = eval_columns(llm, a.limit)
        print("columns", {k: v for k, v in out["column_mapping"].items() if k != "errors"})
    if "routing" in a.tasks:
        out["routing"] = eval_routing(llm)
        print("routing", {k: v for k, v in out["routing"].items() if k != "rows"})
    out["elapsed_s"] = round(time.time() - t0, 1)
    out["llm_calls"] = llm.calls if llm else 0
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RESULTS_DIR / f"llm_eval_{a.label}.json"
    merged = json.loads(path.read_text()) if path.exists() else {}
    merged.update(out)   # partial reruns replace only the tasks they ran
    path.write_text(json.dumps(merged, indent=2))
    print(f"-> {path}  ({out['elapsed_s']}s)")


if __name__ == "__main__":
    main()
