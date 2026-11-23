"""Exhaustive query test generated from the database: every measure x level x question form.

Unlike the hand-written sets, the questions are generated from what the knowledge base holds, so no measure,
level or form is skipped. Each answer is checked automatically:

  dead_end      the knowledge base has the measure but the answer is a bare "No data" (no fallback, no explanation)
  wrong_measure the plan uses a different measure or item than the question names
  silent_level  a ranking at another level than the one asked for, without a "Note:" saying so
  silent_place  a lookup / trend for another place than the one asked for, without a "Note:"
  bad_value     an area larger than the UT, a negative count, or a percentage over 100 in the answer rows
  crash         "Query failed" or an exception
  vague_guess   a question with no measure and no item ("which zone is the best") answered with a guessed measure

  python scripts/query_matrix.py                      # rules planner, all questions
  python scripts/query_matrix.py --planner hybrid --adapter adapters/34_AN_qlora_v2 --sample 4
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

# how a person would name each measure (one everyday phrase each; synonyms are covered by the battery)
PHRASE = {
    "farmers_count": "farmers", "households": "households", "population": "population",
    "livestock_count": "livestock", "poultry_count": "poultry", "fish_landed": "fish landed",
    "forest_area": "forest area", "geographical_area": "geographical area",
    "area_under_cultivation": "area under cultivation", "tractor_count": "tractors",
    "power_tiller_count": "power tillers", "pump_set_count": "pump sets", "kcc_count": "kisan credit cards",
    "godown_count": "godowns", "check_dam_count": "check dams", "fertilizer_consumption": "fertilizer consumption",
    "seedling_distributed": "seedlings distributed", "vermi_bed_count": "vermicompost beds",
    "agri_depot_count": "agriculture depots", "agri_farm_count": "agricultural farms",
    "organic_farm_count": "organic farms", "non_organic_farm_count": "non organic farms", "well_count": "wells",
    "pond_count": "ponds", "manure_unit_count": "manure units", "agri_power_connections": "agricultural power connections",
    "pesticide_distributed": "pesticide distributed", "lulc_area": "land use land cover",
    "land_use_area": "land utilisation", "holdings_count": "operational holdings",
    "holdings_area": "area of operational holdings", "scheme_outlay": "scheme outlay",
    "scheme_expenditure": "scheme expenditure",
}
ITEM_METRICS = {"production": "{c} production", "area_cultivated": "area under {c}", "yield": "yield of {c}",
                "cost_of_cultivation": "cost of cultivation of {c}", "seed_distributed": "{c} seed distributed",
                "retail_price": "price of {c}"}
CROPS = {"paddy": "paddy", "coconut": "coconut", "arecanut": "arecanut", "banana": "banana", "ginger": "ginger"}
PRICE_ITEMS = {"onion": "onion", "eggs": "eggs", "rice": "rice", "milk": "milk", "tomato": "tomato"}
LEVEL_WORD = {"district": "district", "agri_zone": "zone", "island": "island"}
PLACES = {"AN": "andaman and nicobar", "AN_SA": "south andaman district", "AN_NIC": "nicobar district",
          "ZN_DIGLIPUR": "diglipur", "ISL_CARNICOBAR": "car nicobar", "ISL_SWARAJ": "havelock",
          "ISL_MIDDLEANDAMAN": "middle andaman island"}
AREA_METRICS = {"geographical_area", "forest_area", "area_under_cultivation", "land_use_area", "lulc_area",
                "area_cultivated", "holdings_area"}
VAGUE = ["which zone is the best", "which island is the best", "which district is the best", "which zone has the most crops",
         "tell me about car nicobar", "what about diglipur", "which is the top zone", "best island for farming"]


def generate(agent: QueryAgent) -> list[dict]:
    R = agent.R
    out = []
    metrics = [m for m in R.metric_name if m in R.item_free or m in R.item_optional or m in PHRASE]
    targets = [(m, None, PHRASE[m]) for m in metrics if m in PHRASE]
    for m, tpl in ITEM_METRICS.items():
        for cid, word in (PRICE_ITEMS if m == "retail_price" else CROPS).items():
            cid = "paddy" if cid == "rice" and m != "retail_price" else cid
            if m in R.com_metrics.get(cid, ()) or (m == "retail_price" and cid == "rice"):
                targets.append((m, cid, tpl.format(c=word)))
    for m, cid, ph in targets:
        e = {"metric": m, "commodity": cid}
        if m != "retail_price":
            for lvl, w in LEVEL_WORD.items():
                out += [{"q": f"which {w} has the most {ph}", "form": "rank", "level": lvl, **e},
                        {"q": f"{ph} by {w}", "form": "rank", "level": lvl, **e},
                        {"q": f"which {w} has the least {ph}", "form": "rank", "level": lvl, **e}]
            for loc, name in PLACES.items():
                out.append({"q": f"{ph} in {name}", "form": "lookup", "location": loc, **e})
            out += [{"q": f"{ph} in {PLACES['AN_SA']} in 2023-24", "form": "lookup", "location": "AN_SA", **e},
                    {"q": f"{ph} trend in {PLACES['AN']}", "form": "trend", "location": "AN", **e},
                    {"q": f"how has {ph} in {PLACES['ISL_CARNICOBAR']} changed", "form": "trend",
                     "location": "ISL_CARNICOBAR", **e},
                    {"q": f"where does the {ph} figure for {PLACES['AN_NIC']} come from", "form": "provenance",
                     "location": "AN_NIC", **e}]
        else:
            out += [{"q": ph, "form": "lookup", **e}, {"q": f"{ph} in March 2024", "form": "lookup", **e},
                    {"q": f"{ph} trend in 2024", "form": "trend", **e},
                    {"q": f"{ph} over the last 3 years", "form": "trend", **e},
                    {"q": f"when was {ph.replace('price of ', '')} most expensive", "form": "trend", **e}]
    out += [{"q": v, "form": "vague"} for v in VAGUE]
    return out


def judge(agent: QueryAgent, it: dict, ans) -> list[str]:
    R, plan, txt = agent.R, ans.plan or {}, ans.text
    if "Query failed" in txt or ans.error:
        return ["crash"]
    if it["form"] == "vague":
        return [] if ans.query_type == "out_of_scope" else ["vague_guess"]
    if ans.query_type == "out_of_scope":
        return ["refused"]
    bad = []
    m_used = plan.get("metric")
    if m_used != it["metric"] and not (it["metric"] == "yield" and m_used == "production" and "Note:" in txt):
        bad.append("wrong_measure")
    want_c = it.get("commodity")
    if want_c and plan.get("commodity") not in (want_c,) and not (want_c == "rice" and plan.get("commodity") == "rice"):
        bad.append("wrong_item")
    if not ans.rows and agent.availability(it["metric"], want_c)["levels"]:
        if "published by" not in txt and "do not report" not in txt:
            bad.append("dead_end")
        else:
            bad.append("explained_empty")     # allowed, counted separately
    if it["form"] == "rank" and ans.rows and plan.get("level") != it["level"] and "Note:" not in txt:
        bad.append("silent_level")
    loc = it.get("location")
    if loc and ans.rows and it["form"] != "rank":
        got = ans.rows[0].get("location_id")
        family = {loc} | {i for a, ids in R.alias.get("location", {}).items()
                          if any(a == x or a.startswith(x + " ") for x in [PLACES.get(loc, "")]) for i in ids}
        if got not in family and "Note:" not in txt:
            bad.append("silent_place")
    for r in ans.rows:
        v, u = r.get("value_std", r.get("value")), r.get("unit_std", r.get("unit_id"))
        if v is None:
            continue
        if (u == "sq_km" and v > 8249 * 1.01) or (u == "ha" and v > 824900 * 1.01) or (u == "percent" and v > 100) \
                or (u == "count" and v < 0):
            bad.append("bad_value")
            break
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", default="rules")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--sample", type=int, default=1, help="run every n-th question (for the slower model planner)")
    a = ap.parse_args()
    llm = None
    if a.planner != "rules":
        from agri.llm.client import LLM
        llm = LLM(adapter_path=a.adapter)
    agent = QueryAgent(planner=a.planner, llm=llm, few_shot=False)
    items = generate(agent)[::a.sample]
    results, kinds = [], Counter()
    for it in items:
        ans = agent.ask(it["q"])
        bad = judge(agent, it, ans)
        hard = [b for b in bad if b != "explained_empty"]
        kinds.update(bad)
        results.append({**it, "ok": not hard, "issues": bad, "planner": ans.planner, "plan": ans.plan,
                        "answer": ans.text[:300]})
        if hard:
            print(f"FAIL {hard}  {it['q']!r}\n     plan={ {k: ans.plan.get(k) for k in ('intent', 'metric', 'commodity', 'location', 'level')} }"
                  f"\n     {ans.text[:160]!r}")
    n_ok = sum(r["ok"] for r in results)
    print(f"\n{n_ok}/{len(results)} pass ({100 * n_ok / len(results):.1f}%)  issues: {dict(kinds)}")
    label = a.label or a.planner
    path = config.RESULTS_DIR / "phase3" / f"query_matrix_{label}.json"
    path.write_text(json.dumps({"n": len(results), "n_pass": n_ok, "issues": dict(kinds), "items": results},
                               indent=1, ensure_ascii=False, default=str))
    print("->", path)


if __name__ == "__main__":
    main()
