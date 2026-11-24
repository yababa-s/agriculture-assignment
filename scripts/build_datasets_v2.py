"""Training data for adapter v2 (multi-task): v1 tasks + document routing + query planning.

Why: adapter v1 was trained on island extraction and column mapping only. On tasks it never saw it got
worse than the base model (routing valid-id rate 1.0 -> 0.2; query planning answer accuracy 0.80 -> 0.33).
v2 adds those tasks so one adapter serves every LLM decision in the system.

Separation from evaluation:
  * v1 examples: TRAIN documents only (unchanged, data/training/).
  * routing: fingerprints of the 6 TRAIN documents only; routing is then evaluated on the other 14 files.
  * query planning: questions generated from templates and vocabulary written for training; every
    generated question is compared with the 45 dev/test questions and dropped if rapidfuzz ratio >= 80.

Writes data/training_v2/{train,valid}.jsonl and data/training_v2/contamination_report.json.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapidfuzz import fuzz  # noqa: E402

from agri import config  # noqa: E402
from agri.agents.router import SYSTEM as ROUTER_SYSTEM  # noqa: E402
from agri.agents.router import router_prompt
from agri.query.agent import PLANNER_SYSTEM  # noqa: E402

RND = random.Random(407)
OUT = config.ROOT / "data" / "training_v2"
SPLITS = json.loads(config.SPLITS_PATH.read_text(encoding="utf-8"))
TRAIN_DOCS = SPLITS["train"]["island"] + SPLITS["train"]["tables"]

CROPS = ["paddy", "arecanut", "coconut", "banana", "ginger", "black pepper", "maize", "mango", "papaya", "cashewnut",
         "turmeric", "green gram", "tapioca", "sweet potato", "pineapple", "clove", "nutmeg", "cinnamon", "black gram",
         "sapota", "guava", "chilli", "colocasia", "betel leaf"]
PRICE_ITEMS = ["onion", "tomato", "potato", "brinjal", "garlic", "cabbage", "eggs", "green chilli", "rice", "sugar",
               "mutton", "carrot", "cauliflower", "lemon", "apple", "beans", "cucumber", "milk", "atta", "dal"]
HI_CROPS = {"paddy": "धान", "arecanut": "सुपारी", "coconut": "नारियल", "banana": "केला", "mango": "आम"}
HI_LOC = {"South Andaman district": "दक्षिण अण्डमान", "Nicobar district": "निकोबार", "N & M Andaman district": "उत्तर और मध्य अण्डमान"}
CROP_METRICS = {"production": ["production", "output", "total produce", "harvest"],
                "area_cultivated": ["area", "area under cultivation", "acreage", "hectares sown"],
                "yield": ["yield", "productivity"]}
PLAIN_METRICS = {"farmers_count": ["farmers", "farmer households", "cultivators"],
                 "organic_farm_count": ["organic farms"], "poultry_count": ["poultry birds", "poultry"],
                 "population": ["people", "population"], "households": ["households", "homes"],
                 "forest_area": ["forest cover", "forest area"], "livestock_count": ["livestock", "cattle and goats"],
                 "tractor_count": ["tractors"], "kcc_count": ["Kisan Credit Cards", "KCC holders"],
                 "fish_landed": ["fish landed", "fish catch"]}
LEVELS = {"agri_zone": ["agri zone", "agriculture zone", "zone"], "district": ["district"], "island": ["island"],
          "tehsil": ["tehsil"]}
DISTRICTS = ["South Andaman district", "Nicobar district", "N & M Andaman district", "North and Middle Andaman"]
ZONES = ["Diglipur", "Mayabunder", "Rangat", "Little Andaman", "Car Nicobar", "Campbell Bay", "Kamorta"]
ISLANDS = ["Havelock", "Neil Island", "Baratang Island", "Little Andaman Island", "Car Nicobar Island", "Katchal Island",
           "Great Nicobar Island", "North Andaman Island", "Middle Andaman Island", "Long Island", "Rutland Island"]
PLACES = ["Port Blair", "Diglipur", "Car Nicobar", "Campbell Bay", "Rangat", "Mayabunder", "Hut Bay"]
UT = ["the UT", "A&N", "the Andaman and Nicobar Islands", "the whole territory", "Andaman & Nicobar"]
YEARS = ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]


def plan(intent, metric, commodity=None, location=None, level=None, period=None, start=None, end=None, top_k=10,
         order="desc", radius=None) -> dict:
    return {"intent": intent, "metric": metric, "commodity": commodity, "location": location, "level": level,
            "period": period, "start": start, "end": end, "top_k": top_k, "order": order, "radius_km": radius}


def month() -> str:
    return f"{RND.choice(MONTHS)} {RND.choice([2023, 2024, 2025])}"


def gen_one() -> tuple[str, dict]:
    k = RND.random()
    c, m = RND.choice(CROPS), RND.choice(list(CROP_METRICS))
    mw = RND.choice(CROP_METRICS[m])
    pm, pmw = RND.choice(list(PLAIN_METRICS)), None
    pmw = RND.choice(PLAIN_METRICS[pm])
    y = RND.choice(YEARS)
    if k < 0.20:                                  # rank, crop
        lv = RND.choice(["agri_zone", "district"])
        lw = RND.choice(LEVELS[lv])
        order = RND.choice(["desc", "desc", "asc"])
        sup = "highest" if order == "desc" else RND.choice(["lowest", "smallest"])
        t = RND.choice([f"Which {lw} reported the {sup} {c} {mw} in {y}?", f"Order the {lw}s by {c} {mw} ({y})",
                        f"{c.capitalize()} {mw} across {lw}s for {y}", f"In {y}, which {lw} led on {c} {mw}?" if order == "desc"
                        else f"In {y}, which {lw} trailed on {c} {mw}?"])
        return t, plan("rank", m, c, None, lv, y, order=order)
    if k < 0.30:                                  # rank, non-crop at island level
        n = RND.choice([3, 5, 10])
        t = RND.choice([f"List the {n} islands with the most {pmw} in {y}", f"Islands ranked by {pmw}, {y}",
                        f"Biggest islands by {pmw} in {y}?"])
        return t, plan("rank", pm, None, None, "island", y, top_k=n if "List" in t else 10)
    if k < 0.45:                                  # trend
        y1, y2 = sorted(RND.sample(YEARS, 2))
        loc = RND.choice(UT + DISTRICTS)
        t = RND.choice([f"Track {c} {mw} in {loc} from {y1} to {y2}", f"Has {c} {mw} in {loc} gone up or down since {y1}?",
                        f"Year-wise {c} {mw} for {loc}", f"{c.capitalize()} {mw} of {loc}, {y1} through {y2}"])
        start = y1 if ("from" in t or "since" in t or "through" in t) else None
        end = y2 if ("from" in t or "through" in t) else None
        return t, plan("trend", m, c, None if loc in UT else loc, None, None, start, end)
    if k < 0.55:                                  # price trend
        it = RND.choice(PRICE_ITEMS)
        m1, m2 = month(), month()
        t = RND.choice([f"Month-wise {it} price between {m1} and {m2}", f"Plot the {it} rate from {m1} to {m2}",
                        f"When was {it} costliest between {m1} and {m2}?"])
        return t, plan("trend", "retail_price", it, None, None, None, m1, m2)
    if k < 0.70:                                  # provenance
        loc = RND.choice(UT + DISTRICTS + ZONES)
        t = RND.choice([f"Point me to the page that gives the {y} {c} {mw} for {loc}",
                        f"Which publication is the {y} {c} {mw} of {loc} taken from?",
                        f"Show the source cell for {loc}'s {c} {mw} in {y}",
                        f"Trace the {y} figure for {c} {mw} ({loc}) back to its document"])
        return t, plan("provenance", m, c, None if loc in UT else loc, None, y)
    if k < 0.77:                                  # compare sources
        loc = RND.choice(UT + DISTRICTS)
        t = RND.choice([f"Do the publications report the same {c} {mw} for {loc}?",
                        f"Check {c} {mw} of {loc} for disagreement between reports",
                        f"Is there any conflict between sources on {loc} {c} {mw}?"])
        return t, plan("compare_sources", m, c, None if loc in UT else loc)
    if k < 0.85:                                  # nearby
        r = RND.choice([25, 40, 75, 100, 120, 200])
        p = RND.choice(PLACES)
        t = RND.choice([f"{pmw.capitalize()} on islands within {r} km of {p}", f"Islands no more than {r} km from {p}: {pmw}",
                        f"Within {r} km of {p}, which islands have most {pmw}?"])
        return t, plan("nearby", pm, None, p, "island", None, radius=r)
    if k < 0.95:                                  # lookup
        if RND.random() < 0.5:
            loc = RND.choice(DISTRICTS + ZONES)
            t = RND.choice([f"{c.capitalize()} {mw} of {loc} in {y}?", f"Give me {loc}'s {c} {mw} for {y}",
                            f"What did {loc} record for {c} {mw} in {y}?"])
            return t, plan("lookup", m, c, loc, None, y)
        isl = RND.choice(ISLANDS)
        t = RND.choice([f"Number of {pmw} on {isl} in {y}", f"{isl}: {pmw} in {y}?", f"Tell me the {pmw} count of {isl} ({y})"])
        return t, plan("lookup", pm, None, isl, None, y)
    # Hindi
    hc = RND.choice(list(HI_CROPS))
    hl = RND.choice(list(HI_LOC))
    y1, y2 = sorted(RND.sample(YEARS, 2))
    t, p = RND.choice([
        (f"{y} में {HI_LOC[hl]} जिले में {HI_CROPS[hc]} का उत्पादन कितना था?", plan("lookup", "production", hc, hl, None, y)),
        (f"{y1} से {y2} के बीच {HI_CROPS[hc]} का क्षेत्रफल कैसे बदला?", plan("trend", "area_cultivated", hc, None, None, None, y1, y2)),
        (f"{y} में किस जिले में {HI_CROPS[hc]} का उत्पादन सबसे अधिक रहा?", plan("rank", "production", hc, None, "district", y)),
    ])
    return t, p


def chat(system: str, user: str, answer) -> dict:
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user},
                         {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]}


def main() -> None:
    held = [x["question"] for f in ("queries.json", "queries_test.json")
            for x in json.loads((config.GOLD_DIR / f).read_text(encoding="utf-8"))["queries"]]
    seen, q_examples, dropped = set(), [], []
    while len(q_examples) < 200:
        t, p = gen_one()
        if t in seen:
            continue
        seen.add(t)
        best = max(fuzz.ratio(t.lower(), h.lower()) for h in held)
        if best >= 80:
            dropped.append({"question": t, "max_ratio_vs_heldout": best})
            continue
        q_examples.append(chat(PLANNER_SYSTEM, f"Q: {t}\nA:", p))

    fps = json.loads((config.RESULTS_DIR / "fingerprints.json").read_text(encoding="utf-8"))
    routing_gold = {g["document_id"]: g["expected_agent"] for g in json.loads((config.GOLD_DIR / "routing.json").read_text(encoding="utf-8"))}
    r_examples = [chat(ROUTER_SYSTEM, router_prompt(fps[d]), {"agent": routing_gold[d], "reason": "matches the layout"})
                  for d in TRAIN_DOCS]

    v1 = [json.loads(x) for f in ("train.jsonl", "valid.jsonl")
          for x in (config.ROOT / "data" / "training" / f).read_text(encoding="utf-8").splitlines()]
    v1_train = [json.loads(x) for x in (config.ROOT / "data" / "training" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    v1_valid = v1[len(v1_train):]
    RND.shuffle(q_examples)
    q_valid, q_train = q_examples[:20], q_examples[20:]
    # routing examples are few: repeat them so the task is not drowned out
    train = v1_train + q_train + r_examples * 3
    valid = v1_valid + q_valid
    RND.shuffle(train)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "train.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in train) + "\n", encoding="utf-8")
    (OUT / "valid.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in valid) + "\n", encoding="utf-8")
    max_ratio = max(max(fuzz.ratio(json.loads(json.dumps(e))["messages"][1]["content"][3:-3].lower(), h.lower()) for h in held)
                    for e in q_examples)
    report = {"n_train": len(train), "n_valid": len(valid),
              "composition": {"v1_island_and_columns": len(v1_train), "query_planning": len(q_train),
                              "routing (6 train docs x3)": len(r_examples) * 3},
              "query_questions_dropped_as_too_similar": len(dropped), "dropped_examples": dropped[:10],
              "max_similarity_kept_vs_heldout": max_ratio, "routing_train_documents": TRAIN_DOCS,
              "routing_eval_documents": [d for d in routing_gold if d not in TRAIN_DOCS]}
    (OUT / "contamination_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "dropped_examples"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
