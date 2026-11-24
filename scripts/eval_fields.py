"""Per-agent field-level extraction evaluation against hand-transcribed gold (data/gold/field_gold.json).

For each agent: n gold facts, n extracted records in the region, precision, recall, F1 (with a 95%
bootstrap interval over facts), provenance accuracy (a correct record cites the gold page and its printed
text is on that page), and an error breakdown. Macro-average over agents.

Error types (assigned automatically, checked by hand for the report):
  value      right key (metric, item, place, period), wrong number   -> OCR / parsing / cell shift
  location   right metric, item, period and value, wrong place        -> header/column mapping
  period     right everything but period                               -> year/column mapping
  metric     right item, place, period and value, wrong metric         -> header mapping
  spurious   record matching no gold fact at all                       -> layout noise (footers, totals)
  missed     gold fact with no record                                  -> extraction gap

  python scripts/eval_fields.py [--db db/34_AN_knowledgebase_v1.sqlite] [--label v1]
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402

OUT = config.RESULTS_DIR / "phase3"


def close(a, b, tol=0.005) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(tol * abs(b), 1e-6)


def _dims_ok(gold_dims: dict, rec_dims: dict) -> bool:
    norm = lambda s: " ".join(str(s).lower().split())  # noqa: E731
    return all(norm(rec_dims.get(k, "")) == norm(v) for k, v in (gold_dims or {}).items())


def region_records(conn, reg: dict) -> list[dict]:
    q = ("SELECT obs_id, metric_id, commodity_id, location_id, period_label, dims, value, value_raw, page "
         f"FROM observation WHERE document_id=? AND page IN ({','.join('?' * len(reg['pages']))}) AND value IS NOT NULL")
    params = [reg["document_id"], *reg["pages"]]
    f = reg.get("filter") or {}
    if f.get("commodity"):
        q += f" AND commodity_id IN ({','.join('?' * len(f['commodity']))})"
        params += f["commodity"]
    if f.get("metric"):
        q += f" AND metric_id IN ({','.join('?' * len(f['metric']))})"
        params += f["metric"]
    rows = [dict(r) for r in conn.execute(q, params)]
    for r in rows:
        r["dims"] = json.loads(r["dims"] or "{}")
    return rows


def match(gold: list[dict], recs: list[dict]) -> tuple[list[tuple], list[dict], list[dict]]:
    """Greedy one-to-one matching. Returns (pairs, unmatched_gold, unmatched_records)."""
    used, pairs, missed = set(), [], []
    for g in gold:
        hit = None
        for r in recs:
            if r["obs_id"] in used:
                continue
            if (r["metric_id"] == g["metric"] and r["commodity_id"] == g.get("commodity") and r["location_id"] == g["location"]
                    and r["period_label"] == g["period"] and _dims_ok(g.get("dims"), r["dims"]) and close(r["value"], g["value"])):
                hit = r
                break
        if hit:
            used.add(hit["obs_id"])
            pairs.append((g, hit))
        else:
            missed.append(g)
    extra = [r for r in recs if r["obs_id"] not in used]
    return pairs, missed, extra


def classify(r: dict, gold: list[dict]) -> str:
    key = lambda g: (g["metric"], g.get("commodity"), g["location"], g["period"])  # noqa: E731
    rk = (r["metric_id"], r["commodity_id"], r["location_id"], r["period_label"])
    for g in gold:
        if key(g) == rk and _dims_ok(g.get("dims"), r["dims"]):
            return "value"
    for g in gold:
        if not close(r["value"], g["value"]):
            continue
        same = [r["metric_id"] == g["metric"], r["commodity_id"] == g.get("commodity"), r["location_id"] == g["location"],
                r["period_label"] == g["period"]]
        if sum(same) == 3:
            return ["metric", "commodity", "location", "period"][same.index(False)]
    return "spurious"


def prf(tp: int, n_pred: int, n_gold: int) -> tuple[float, float, float]:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def bootstrap_f1(gold_hit: list[int], n_extra: int, b: int = 2000, seed: int = 407) -> tuple[float, float]:
    """Resample gold facts (hit/miss) and spurious records together; 95% percentile interval of F1."""
    rnd = random.Random(seed)
    units = [("g", h) for h in gold_hit] + [("x", 0)] * n_extra
    f1s = []
    for _ in range(b):
        s = [units[rnd.randrange(len(units))] for _ in units]
        tp = sum(h for k, h in s if k == "g")
        n_gold = sum(1 for k, _ in s if k == "g")
        n_pred = tp + sum(1 for k, _ in s if k == "x")
        f1s.append(prf(tp, n_pred, n_gold)[2])
    f1s.sort()
    return round(f1s[int(0.025 * b)], 3), round(f1s[int(0.975 * b) - 1], 3)


def page_text(conn, doc: str, page: int) -> str:
    r = conn.execute("SELECT text FROM document_chunk WHERE document_id=? AND page=?", (doc, page)).fetchone()
    return r[0] if r and r[0] else ""


def island_region(conn) -> tuple[dict, list[dict], list[dict]]:
    g = json.loads((config.ROOT / "data" / "gold" / "island_profiles_D10.json").read_text(encoding="utf-8"))
    gold = [{"metric": it["metric"], "commodity": None, "location": blk["island"], "period": None, "value": it["value"],
             "page": blk["page"]} for blk in g["blocks"] for it in blk["items"] if it["value"] is not None]
    recs = [dict(r) for r in conn.execute(
        "SELECT o.obs_id, o.metric_id, o.commodity_id, o.location_id, o.period_label, o.dims, o.value, o.value_raw, o.page "
        "FROM observation o JOIN location l ON l.location_id=o.location_id WHERE o.document_id='D10' AND l.level='island' "
        "AND o.value IS NOT NULL")]
    for r in recs:
        r["dims"] = {}
        r["period_label"] = None   # island gold has no period (one profile year); compare on place, metric, value
    reg = {"agent": "island_profile_agent", "document_id": "D10", "pages": sorted({x["page"] for x in gold}),
           "language": "en+hi", "note": "data/gold/island_profiles_D10.json (31 islands)"}
    return reg, gold, recs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(config.DB_PATH))
    ap.add_argument("--label", default=config.DB_VERSION)
    a = ap.parse_args()
    conn = sqlite3.connect(a.db)
    conn.row_factory = sqlite3.Row
    spec = json.loads((config.ROOT / "data" / "gold" / "field_gold.json").read_text(encoding="utf-8"))
    cases = [(reg, reg["facts"], region_records(conn, reg)) for reg in spec["regions"]]
    cases.insert(3, island_region(conn))
    per_agent, examples = [], {}
    for reg, gold, recs in cases:
        pairs, missed, extra = match(gold, recs)
        tp = len(pairs)
        p, r, f1 = prf(tp, len(recs), len(gold))
        hit = [1] * tp + [0] * len(missed)
        lo, hi = bootstrap_f1(hit, len(extra))
        prov_ok = 0
        for g, rec in pairs:
            text = page_text(conn, reg["document_id"], rec["page"])
            page_ok = rec["page"] in reg["pages"] and (not g.get("page") or rec["page"] == g["page"])
            prov_ok += page_ok and (not text or str(rec["value_raw"]).strip() in text)
        errs = Counter(classify(x, gold) for x in extra)
        errs["missed"] = len(missed) - sum(v for k, v in errs.items() if k in ("value", "location", "period", "metric", "commodity"))
        errs = {k: v for k, v in errs.items() if v > 0}
        per_agent.append({"agent": reg["agent"], "document_id": reg["document_id"], "pages": reg["pages"],
                          "language": reg.get("language"), "n_gold": len(gold), "n_extracted": len(recs), "tp": tp,
                          "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3), "f1_ci95": [lo, hi],
                          "provenance_accuracy": round(prov_ok / tp, 3) if tp else None, "errors": errs,
                          "note": reg.get("note")})
        examples[reg["agent"]] = {"spurious_or_wrong": [{k: x[k] for k in ("metric_id", "commodity_id", "location_id",
                                                                           "period_label", "value", "value_raw", "page")}
                                                        for x in extra[:5]],
                                  "missed": missed[:5]}
    macro = {k: round(statistics.mean(x[k] for x in per_agent), 3) for k in ("precision", "recall", "f1")}
    macro["provenance_accuracy"] = round(statistics.mean(x["provenance_accuracy"] for x in per_agent if x["provenance_accuracy"] is not None), 3)
    tot_tp = sum(x["tp"] for x in per_agent)
    micro = dict(zip(("precision", "recall", "f1"), (round(v, 3) for v in prf(tot_tp, sum(x["n_extracted"] for x in per_agent),
                                                                               sum(x["n_gold"] for x in per_agent)))))
    err_total = Counter()
    for x in per_agent:
        err_total.update(x["errors"])
    out = {"label": a.label, "db": Path(a.db).name, "per_agent": per_agent, "macro": macro, "micro": micro,
           "n_gold_total": sum(x["n_gold"] for x in per_agent), "errors_total": dict(err_total), "examples": examples}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"field_eval_{a.label}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"{'agent':<24}{'doc':<5}{'n_gold':>7}{'n_ext':>7}{'P':>7}{'R':>7}{'F1':>7}  {'95% CI':<14}{'prov':>6}  errors")
    for x in per_agent:
        print(f"{x['agent']:<24}{x['document_id']:<5}{x['n_gold']:>7}{x['n_extracted']:>7}{x['precision']:>7}{x['recall']:>7}"
              f"{x['f1']:>7}  {str(x['f1_ci95']):<14}{str(x['provenance_accuracy']):>6}  {x['errors']}")
    print(f"{'macro-average':<36}{'':>7}{macro['precision']:>7}{macro['recall']:>7}{macro['f1']:>7}  {'':<14}{macro['provenance_accuracy']:>6}")
    print(f"micro: {micro}   errors: {dict(err_total)}   -> {path}")


if __name__ == "__main__":
    main()
