"""Query Agent: answers natural-language questions about the knowledge base, with provenance.

    question ─▶ planner ─▶ resolver ─▶ typed tool (read-only SQL) ─▶ answer composer
               model|rules   code            code                       code (template)

* Planner (decided by MODEL when an LLM is available, by RULES otherwise): reads the question and
  returns a JSON plan: intent, metric, commodity, location, level, period(s), top_k, order, radius.
  An invalid model plan falls back to the rule planner (logged as planner=model->rules).
* Resolver (CODE): maps the plan's words to canonical ids through the alias table (English + Hindi)
  and a small query-synonym list; never invents ids.
* Tools (CODE): fixed, parameterised SQL in agri/query/tools.py on a read-only connection.
* Composer (CODE): every answer states the number, unit, period and the document, page, table,
  row and column it came from. The model never writes a number.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rapidfuzz import fuzz, process

from agri import config
from agri.query import tools as T

INTENTS = {"rank": "spatial", "nearby": "spatial", "trend": "temporal", "provenance": "provenance",
           "compare_sources": "cross_source", "lookup": "lookup"}

# Query words -> metric ids (checked longest first). The alias table covers document labels; these
# cover how people phrase questions.
METRIC_SYNONYMS = {
    "retail price": "retail_price", "price": "retail_price", "expensive": "retail_price", "cheapest": "retail_price",
    "costliest": "retail_price", "cheap": "retail_price", "cost per kg": "retail_price", "rate": "retail_price",
    "दाम": "retail_price", "कीमत": "retail_price", "मूल्य": "retail_price",
    "area under cultivation": "area_under_cultivation", "cultivated area": "area_under_cultivation",
    "area under": "area_cultivated", "area": "area_cultivated", "hectare": "area_cultivated", "क्षेत्रफल": "area_cultivated",
    "production": "production", "produce": "production", "output": "production", "उत्पादन": "production",
    "yield": "yield", "productivity": "yield", "उपज": "yield",
    "farmers": "farmers_count", "cultivators": "farmers_count", "किसान": "farmers_count",
    "organic farms": "organic_farm_count", "organic": "organic_farm_count",
    "non-organic farms": "non_organic_farm_count", "non organic": "non_organic_farm_count",
    "population": "population", "households": "households", "livestock": "livestock_count",
    "poultry": "poultry_count", "fish landed": "fish_landed", "fish catch": "fish_landed",
    "forest": "forest_area", "geographical area": "geographical_area",
    "tractors": "tractor_count", "power tillers": "power_tiller_count", "pump sets": "pump_set_count",
    "kisan credit": "kcc_count", "kcc": "kcc_count", "godowns": "godown_count", "check dams": "check_dam_count",
    "fertilizer": "fertilizer_consumption", "fertiliser": "fertilizer_consumption",
    "seedlings": "seedling_distributed", "vermi": "vermi_bed_count", "depots": "agri_depot_count",
    "land use": "lulc_area", "land cover": "lulc_area", "lulc": "lulc_area",
    "cost of cultivation": "cost_of_cultivation", "holdings": "holdings_count",
    "scheme outlay": "scheme_outlay", "budget": "scheme_outlay", "expenditure": "scheme_expenditure",
}
LEVEL_WORDS = {"zone": "agri_zone", "zones": "agri_zone", "agri zone": "agri_zone", "district": "district",
               "districts": "district", "island": "island", "islands": "island", "tehsil": "tehsil",
               "tehsils": "tehsil", "जिला": "district", "जिले": "district", "द्वीप": "island"}
NON_COMMODITY = {m for m in ("farmers_count", "organic_farm_count", "non_organic_farm_count", "population",
                             "households", "livestock_count", "poultry_count", "fish_landed", "forest_area",
                             "geographical_area", "tractor_count", "power_tiller_count", "pump_set_count",
                             "kcc_count", "godown_count", "check_dam_count", "fertilizer_consumption",
                             "vermi_bed_count", "agri_depot_count", "lulc_area", "area_under_cultivation",
                             "holdings_count", "scheme_outlay", "scheme_expenditure")}
PRICE_METRICS = {"retail_price", "wholesale_price"}
_STOP_ALIASES = {"total", "grand total", "ut total", "east", "long", "aves", "smith", "a", "an", "rate", "others"}
MONTHS = T._MONTHS
RANK_WORDS = ("which district", "which zone", "which agri zone", "which island", "which tehsil", "top ", "highest",
              "most", "largest", "biggest", "lowest", "least", "fewest", "smallest", "rank", "by zone", "by district",
              "by island", "compare the", "कौन", "सबसे")


@dataclass
class Plan:
    intent: str
    metric: str | None = None
    commodity: str | None = None
    location: str | None = None
    level: str | None = None
    period: str | None = None
    start: str | None = None
    end: str | None = None
    top_k: int = 10
    order: str = "desc"
    radius_km: float | None = None
    confident: bool = True       # rule planner: metric and item found explicitly (not defaulted)


@dataclass
class Answer:
    question: str
    query_type: str
    planner: str
    plan: dict
    tool: str
    args: dict
    sql: str
    text: str
    rows: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    citations: list[dict] = field(default_factory=list)
    latency_s: float = 0.0
    query_id: str = ""
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)


# ------------------------------------------------------------------ helpers
def _norm(s: str) -> str:
    s = s.lower().replace("&", " & ").replace("’", "'")
    return " ".join(re.sub(r"[?!,;:()\"]", " ", s).split())


def _find_periods(q: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b((?:19|20)\d\d)\s*[-–/]\s*((?:19|20)?\d\d)\b", q):
        y2 = m.group(2)[-2:]
        out.append(f"{m.group(1)}-{y2}")
    rest = re.sub(r"\b(?:19|20)\d\d\s*[-–/]\s*(?:19|20)?\d\d\b", " ", q)
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\s+((?:19|20)\d\d)\b", rest, re.I):
        out.append(f"{m.group(1).capitalize()} {m.group(2)}")
    rest = re.sub(r"\b(" + "|".join(MONTHS) + r")\s+(?:19|20)\d\d\b", " ", rest, flags=re.I)
    out += re.findall(r"\b((?:19|20)\d\d)\b", rest)
    return out


class Resolver:
    """Words -> canonical ids, using the knowledge base's alias table (English and Hindi)."""

    def __init__(self, conn):
        self.alias: dict[str, dict[str, set[str]]] = {}
        for r in conn.execute("SELECT alias, entity_type, entity_id FROM alias"):
            self.alias.setdefault(r["entity_type"], {}).setdefault(r["alias"], set()).add(r["entity_id"])
        self.level = {r["location_id"]: r["level"] for r in conn.execute("SELECT location_id, level FROM location")}
        self.loc_name = {r["location_id"]: r["name"] for r in conn.execute("SELECT location_id, name FROM location")}
        self.com_name = {r["commodity_id"]: r["name"] for r in conn.execute("SELECT commodity_id, name FROM commodity")}
        self.metric_name = {r["metric_id"]: r["name"] for r in conn.execute("SELECT metric_id, name FROM metric")}
        self.unit_symbol = {r["unit_id"]: r["symbol"] for r in conn.execute("SELECT unit_id, symbol FROM unit")}
        self.observed_commodities = {r[0] for r in conn.execute("SELECT DISTINCT commodity_id FROM observation")}

    # -- free-text scan (rule planner)
    def scan(self, etype: str, q: str) -> list[tuple[str, str]]:
        """All (alias, id) whose alias occurs as whole words in q, longest alias first."""
        hits = []
        for a, ids in self.alias.get(etype, {}).items():
            if len(a) < 3 or a in _STOP_ALIASES:
                continue
            if re.search(r"(?<![\w])" + re.escape(a) + r"(?![\w])", q):
                for i in ids:
                    hits.append((a, i))
        hits.sort(key=lambda h: -len(h[0]))
        return hits

    def commodity_in(self, q: str) -> str | None:
        hits = [h for h in self.scan("commodity", q) if h[1] in self.observed_commodities]
        return hits[0][1] if hits else None

    def location_in(self, q: str, level_hint: str | None) -> str | None:
        hits = self.scan("location", q)
        if not hits:
            return None
        best_len = len(hits[0][0])
        cands = [i for a, i in hits if len(a) == best_len]
        if level_hint:
            pref = [c for c in cands if self.level.get(c) == level_hint]
            if pref:
                return pref[0]
        order = ["district", "island", "agri_zone", "tehsil", "ut", "market"]
        return sorted(cands, key=lambda c: order.index(self.level[c]) if self.level.get(c) in order else 9)[0]

    # -- single value (model plans)
    def resolve(self, etype: str, value: str | None, level_hint: str | None = None) -> str | None:
        if not value:
            return None
        v = _norm(str(value))
        names = {"commodity": self.com_name, "location": self.loc_name, "metric": self.metric_name}[etype]
        if value in names:
            return value
        if etype == "metric":
            for k in sorted(METRIC_SYNONYMS, key=len, reverse=True):
                if k in v:
                    return METRIC_SYNONYMS[k]
        table = self.alias.get(etype, {})
        if v in table:
            ids = sorted(table[v])
            if etype == "location" and level_hint:
                ids = sorted(ids, key=lambda i: self.level.get(i) != level_hint)
            return ids[0]
        pool = {**{_norm(n): i for i, n in names.items()}, **{a: sorted(ids)[0] for a, ids in table.items()}}
        best = process.extractOne(v, list(pool), scorer=fuzz.WRatio)
        return pool[best[0]] if best and best[1] >= 88 else None


# ------------------------------------------------------------------ planners
def rule_plan(question: str, R: Resolver) -> Plan:
    q = _norm(question)
    periods = _find_periods(question)
    level = None
    for w in sorted(LEVEL_WORDS, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", q):
            level = LEVEL_WORDS[w]
            break
    metric = None
    for k in sorted(METRIC_SYNONYMS, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(k), q):
            metric = METRIC_SYNONYMS[k]
            break
    metric_explicit = metric is not None
    commodity = R.commodity_in(q)
    location = R.location_in(q, None)
    if any(w in q for w in ("which source", "which document", "which page", "come from", "came from", "provenance",
                            "where does", "where did", "cite", "source of", "source for", "which report", "which table",
                            "स्रोत", "किस दस्तावेज")):
        intent = "provenance"
    elif any(w in q for w in ("agree", "disagree", "consistent", "differ", "conflict", "compare sources", "both sources",
                              "two sources", "cross-check", "cross check")):
        intent = "compare_sources"
    elif re.search(r"within\s+\d+\s*km|\bnear(by|est)?\b|\bclose to\b", q):
        intent = "nearby"
    elif (len(periods) >= 2 or any(w in q for w in ("trend", "over time", "over the years", "across years", "change",
                                                     "changed", "every year", "each year", "monthly", "month by month",
                                                     "year by year", "series", "since", "rise", "fall", "decline",
                                                     "increase", "decrease", "peak", "बदला", "रुझान"))):
        intent = "trend"
    elif any(w in q for w in RANK_WORDS) or (level and not (location and R.level.get(location) == level)):
        intent = "rank"
    else:
        intent = "lookup"
    if intent == "rank" and location and R.level.get(location) == level:
        location = None                      # "which island ..." names a level, not one place
    if metric is None:
        metric = "retail_price" if commodity and commodity not in _crop_commodities(R) else "production"
    if metric in NON_COMMODITY:
        commodity = None
    if intent in ("trend", "lookup", "provenance", "compare_sources") and not location:
        location = "MKT_AN" if metric in PRICE_METRICS else "AN"
    if metric in PRICE_METRICS and intent != "nearby":
        location = "MKT_AN"
    p = Plan(intent=intent, metric=metric, commodity=commodity, location=location, level=level,
             confident=metric_explicit and (commodity is not None or metric in NON_COMMODITY))
    if intent == "trend":
        p.start, p.end = (periods[0], periods[-1]) if len(periods) >= 2 else (periods[0] if periods else None, None)
    else:
        p.period = periods[0] if periods else None
    m = re.search(r"\btop\s+(\d+)", q)
    if m:
        p.top_k = int(m.group(1))
    if any(w in q for w in ("lowest", "least", "smallest", "minimum", "fewest", "cheapest", "सबसे कम")):
        p.order = "asc"
    m = re.search(r"within\s+(\d+)\s*km", q)
    if m:
        p.radius_km = float(m.group(1))
    elif intent == "nearby":
        p.radius_km = 50.0
    if intent == "nearby" and not p.level:
        p.level = "island"
    return p


def _crop_commodities(R: Resolver) -> set[str]:
    return set(R.observed_commodities) - {None}


PLANNER_SYSTEM = """You turn questions about Andaman & Nicobar agriculture statistics into a JSON query plan.
Reply with ONE JSON object and nothing else:
{"intent": "rank|trend|provenance|compare_sources|nearby|lookup",
 "metric": "<metric id>", "commodity": "<crop or market item, or null>", "location": "<place name, or null>",
 "level": "agri_zone|district|island|tehsil|null", "period": "<e.g. 2025-26, 2024, March 2024, or null>",
 "start": "<first period for trends, or null>", "end": "<last period for trends, or null>",
 "top_k": <int>, "order": "desc|asc", "radius_km": <number or null>}
intent: rank = compare places for one period; trend = values over time for one place; provenance = which
document/page a number came from; compare_sources = do sources agree; nearby = places within a distance;
lookup = one value.
Metric ids: production, area_cultivated, yield, retail_price, farmers_count, organic_farm_count, population,
households, livestock_count, poultry_count, forest_area, geographical_area, area_under_cultivation, lulc_area,
tractor_count, kcc_count, fish_landed, fertilizer_consumption, cost_of_cultivation, scheme_outlay."""

PLANNER_EXAMPLES = [
    ("Which agri zone produced the most paddy in 2025-26?",
     {"intent": "rank", "metric": "production", "commodity": "paddy", "location": None, "level": "agri_zone",
      "period": "2025-26", "start": None, "end": None, "top_k": 10, "order": "desc", "radius_km": None}),
    ("How did the retail price of tomato change from January 2023 to December 2025?",
     {"intent": "trend", "metric": "retail_price", "commodity": "tomato", "location": None, "level": None,
      "period": None, "start": "January 2023", "end": "December 2025", "top_k": 10, "order": "desc", "radius_km": None}),
    ("Which page of which report gives the 2024-25 banana area for the UT?",
     {"intent": "provenance", "metric": "area_cultivated", "commodity": "banana", "location": "Andaman & Nicobar Islands",
      "level": None, "period": "2024-25", "start": None, "end": None, "top_k": 10, "order": "desc", "radius_km": None}),
]


def model_plan(question: str, llm, few_shot: bool = True) -> tuple[dict | None, str]:
    shots = ""
    if few_shot:
        shots = "\n\nExamples:\n" + "\n".join(f"Q: {q}\nA: {json.dumps(a)}" for q, a in PLANNER_EXAMPLES)
    r = llm.json_call(PLANNER_SYSTEM + shots, f"Q: {question}\nA:", max_tokens=220)
    return (r.parsed if r.ok and isinstance(r.parsed, dict) else None), r.text


def plan_from_model(raw: dict, R: Resolver, question: str) -> Plan | None:
    intent = str(raw.get("intent") or "").strip()
    if intent not in INTENTS:
        return None
    level = raw.get("level") if raw.get("level") in T.LEVELS else None
    metric = R.resolve("metric", raw.get("metric"))
    if not metric:
        return None
    commodity = None if metric in NON_COMMODITY else R.resolve("commodity", raw.get("commodity"))
    location = R.resolve("location", raw.get("location"), level)
    if metric in PRICE_METRICS:
        location = "MKT_AN"
    if intent in ("trend", "lookup", "provenance", "compare_sources") and not location:
        location = "AN"
    if intent == "rank" and location and R.level.get(location) in ("ut", "market"):
        location = None
    p = Plan(intent=intent, metric=metric, commodity=commodity, location=location, level=level,
             period=_clean_period(raw.get("period")), start=_clean_period(raw.get("start")),
             end=_clean_period(raw.get("end")))
    try:
        p.top_k = int(raw.get("top_k") or 10)
    except (TypeError, ValueError):
        p.top_k = 10
    p.order = "asc" if str(raw.get("order")).lower() == "asc" else "desc"
    try:
        p.radius_km = float(raw["radius_km"]) if raw.get("radius_km") not in (None, "null") else None
    except (TypeError, ValueError):
        p.radius_km = None
    if intent == "nearby":
        p.radius_km = p.radius_km or 50.0
        p.level = p.level or "island"
    return p


def _clean_period(v) -> str | None:
    if v in (None, "", "null"):
        return None
    ps = _find_periods(str(v))
    return ps[0] if ps else None


# ------------------------------------------------------------------ agent
class QueryAgent:
    def __init__(self, db_path: Path | str = config.DB_PATH, llm=None, planner: str = "auto", few_shot: bool = True):
        """planner: 'hybrid' (rules when confident, else model; deployed) | 'auto' (model, rules on failure)
        | 'model' (no fallback) | 'rules'."""
        self.conn = T.connect_ro(db_path)
        self.R = Resolver(self.conn)
        self.llm = llm
        self.planner = planner
        self.few_shot = few_shot
        self.log_dir = config.LOG_DIR / "queries"

    def plan(self, question: str) -> tuple[Plan | None, str, str]:
        if self.planner == "hybrid":
            rp = rule_plan(question, self.R)
            if rp.confident or self.llm is None or not self.llm.enabled:
                return rp, "rules", ""
            raw, text = model_plan(question, self.llm, self.few_shot)
            p = plan_from_model(raw, self.R, question) if raw else None
            return (p, "rules->model", text) if p else (rp, "rules->model(invalid)->rules", text)
        use_model = self.planner in ("auto", "model") and self.llm is not None and self.llm.enabled
        if use_model:
            raw, text = model_plan(question, self.llm, self.few_shot)
            p = plan_from_model(raw, self.R, question) if raw else None
            if p:
                return p, "model", text
            if self.planner == "model":
                return None, "model(invalid)", text
            return rule_plan(question, self.R), "model->rules", text
        return rule_plan(question, self.R), "rules", ""

    def execute(self, p: Plan) -> T.ToolResult:
        c = self.conn
        if p.intent == "rank":
            return T.rank_locations(c, p.metric, p.commodity, p.period, p.level, p.top_k, p.order)
        if p.intent == "trend":
            return T.time_series(c, p.metric, p.commodity, p.location, p.start, p.end)
        if p.intent == "provenance":
            return T.trace_value(c, p.metric, p.commodity, p.location, p.period)
        if p.intent == "compare_sources":
            return T.compare_sources(c, p.metric, p.commodity, p.location, p.period)
        if p.intent == "nearby":
            ref = p.location if p.location and p.location not in ("AN", "MKT_AN") else "TH_PORTBLAIR"
            return T.nearby(c, ref, p.radius_km or 50.0, p.metric, p.commodity, p.level or "island", p.period)
        return T.trace_value(c, p.metric, p.commodity, p.location, p.period)   # lookup = best-ranked source

    def ask(self, question: str) -> Answer:
        t0 = time.time()
        qid = uuid.uuid4().hex[:10]
        p, planner, raw = self.plan(question)
        if p is None:
            ans = Answer(question, "unknown", planner, {}, "", {}, "", "Sorry, I could not turn this question into a "
                         "query. Try naming a crop or metric, a place and a year.", error=f"invalid plan: {raw[:200]}")
        else:
            try:
                res = self.execute(p)
                text, cites = compose(p, res, self.R)
                ans = Answer(question, INTENTS[p.intent], planner, asdict(p), res.tool, res.args, res.sql.strip(), text,
                             res.rows, res.summary, cites)
            except Exception as e:  # noqa: BLE001 - reported to the user, logged
                ans = Answer(question, INTENTS[p.intent], planner, asdict(p), "", {}, "", f"Query failed: {e}", error=str(e))
        ans.latency_s = round(time.time() - t0, 2)
        ans.query_id = qid
        self._log(ans, raw)
        return ans

    def _log(self, ans: Answer, raw: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "query_id": ans.query_id, "question": ans.question,
               "planner": ans.planner, "model": getattr(self.llm, "label", None) if self.llm else None,
               "raw_model_output": raw[:500], "plan": ans.plan, "tool": ans.tool, "n_rows": len(ans.rows),
               "citations": ans.citations[:5], "latency_s": ans.latency_s, "error": ans.error}
        with (self.log_dir / f"{time.strftime('%Y%m%d')}.jsonl").open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


# ------------------------------------------------------------------ composer
def _fmt(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}".rstrip("0").rstrip(".")


def _cite(r: dict) -> dict:
    return {"obs_id": r.get("obs_id"), "document_id": r.get("document_id"), "file_name": r.get("file_name"),
            "publisher": r.get("publisher"), "page": r.get("page"), "table": r.get("table_ref"),
            "row": r.get("row_label"), "column": r.get("col_label"), "printed": r.get("value_raw"),
            "agent": r.get("agent_id"), "run": r.get("run_id")}


def _cite_txt(r: dict) -> str:
    flag = " ⚠ unverified" if r.get("validation") == "warning" else ""
    return f"[{r['document_id']} p{r['page']}{flag}]"


def compose(p: Plan, res: T.ToolResult, R: Resolver) -> tuple[str, list[dict]]:
    rows = res.rows
    what = R.metric_name.get(p.metric, p.metric) + (f" of {R.com_name.get(p.commodity, p.commodity)}" if p.commodity else "")
    if not rows:
        return (f"No data in the knowledge base for {what}"
                + (f" at {R.loc_name.get(p.location, p.location)}" if p.location else "")
                + (f" in {res.args.get('period') or p.period}" if (res.args.get('period') or p.period) else "") + "."), []
    unit = R.unit_symbol.get(rows[0].get("unit_id"), rows[0].get("unit_id") or "")
    unit = {"MT (tonne)": "t", "number": "", "count": ""}.get(unit, unit)
    if res.tool == "rank_locations":
        lvl = res.summary["level"].replace("agri_zone", "agri zone")
        head = rows[0]
        lines = [f"{what} by {lvl}, {res.summary['period']} ({res.summary['n_locations']} {lvl}s with data): "
                 f"{head['location']} is {'highest' if p.order == 'desc' else 'lowest'} with {_fmt(head['value'])} {unit}"
                 + (f" ({head['share_pct']}% of the total)" if head.get("share_pct") is not None else "") + f" {_cite_txt(head)}."]
        lines += [f"  {i}. {r['location']}: {_fmt(r['value'])} {unit} {_cite_txt(r)}" for i, r in enumerate(rows, 1)]
        return "\n".join(lines), [_cite(r) for r in rows]
    if res.tool == "time_series":
        s = res.summary
        loc = R.loc_name.get(p.location, p.location)
        lines = [f"{what}, {loc}: {_fmt(s['first'][1])} {unit} in {s['first'][0]} -> {_fmt(s['last'][1])} {unit} in "
                 f"{s['last'][0]} ({s['change_pct']:+}% over {s['n_periods']} periods). Peak {_fmt(s['peak'][1])} in "
                 f"{s['peak'][0]}; low {_fmt(s['low'][1])} in {s['low'][0]}. Sources: {', '.join(s['documents'])}."]
        lines += [f"  {r['period_label']}: {_fmt(r['value'])} {unit} {_cite_txt(r)}" for r in rows]
        return "\n".join(lines), [_cite(r) for r in rows]
    if res.tool == "trace_value":
        r0 = rows[0]
        loc = R.loc_name.get(r0["location_id"], r0["location_id"])
        lines = [f"{what}, {loc}, {r0['period_label']} = {_fmt(r0['value'])} {unit}. It comes from {r0['file_name']} "
                 f"({r0['publisher']}), page {r0['page']}, table {r0['table_ref']}, row \"{r0['row_label']}\", column "
                 f"\"{r0['col_label']}\", printed as \"{r0['value_raw']}\"; extracted by {r0['agent_id']} in run {r0['run_id']}."]
        others = [r for r in rows[1:]]
        if others:
            lines.append(f"Also reported by {len({r['document_id'] for r in others})} other document(s):")
            lines += [f"  {r['document_id']} p{r['page']} ({r['table_ref']}): {_fmt(r['value'])} {unit}" for r in others[:8]]
        return "\n".join(lines), [_cite(r) for r in rows]
    if res.tool == "compare_sources":
        s = res.summary
        lines = [f"{what}, {R.loc_name.get(p.location, p.location)}: {s['periods_with_2plus_sources']} period(s) are "
                 f"reported by 2+ documents; {s['periods_agreeing_within_1pct']} agree within 1%."]
        lines += [f"  {r['period_label']}: {r['document_id']} p{r['page']} = {_fmt(r['value'])} {unit} "
                  f"(spread {r['period_spread_pct']}%)" for r in rows]
        return "\n".join(lines), [_cite(r) for r in rows]
    if res.tool == "nearby":
        s = res.summary
        if "value" not in rows[0]:
            return (f"{s['n_within_radius']} {p.level}s within {p.radius_km:g} km of {s['reference']}: "
                    + ", ".join(f"{R.loc_name.get(r['location_id'])} ({r['distance_km']} km)" for r in rows)), []
        lines = [f"{s['n_within_radius']} {p.level}s within {p.radius_km:g} km of {s['reference']}; {what} "
                 f"({rows[0]['period_label']}):"]
        lines += [f"  {r['location']} ({r['distance_km']} km): {_fmt(r['value'])} {unit} {_cite_txt(r)}" for r in rows]
        return "\n".join(lines), [_cite(r) for r in rows]
    return json.dumps(rows[:20], default=str), []
