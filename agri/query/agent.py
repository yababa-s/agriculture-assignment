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
from agri.query.scope import HELP, RELATIVE_TIME, classify

INTENTS = {"rank": "spatial", "nearby": "spatial", "trend": "temporal", "provenance": "provenance",
           "compare_sources": "cross_source", "lookup": "lookup"}

# Query words -> metric ids (checked longest first). The alias table covers document labels; these
# cover how people phrase questions.
METRIC_SYNONYMS = {
    "retail price": "retail_price", "price": "retail_price", "expensive": "retail_price", "cheapest": "retail_price",
    "costliest": "retail_price", "cheap": "retail_price", "cost per kg": "retail_price", "rate": "retail_price",
    "दाम": "retail_price", "कीमत": "retail_price", "मूल्य": "retail_price",
    "area under cultivation": "area_under_cultivation", "cultivated area": "area_under_cultivation",
    "area under agriculture": "area_under_cultivation", "agricultural area": "area_under_cultivation",
    "agricultural land": "area_under_cultivation", "farmland": "area_under_cultivation", "farm land": "area_under_cultivation",
    "cultivated land": "area_under_cultivation", "land under cultivation": "area_under_cultivation",
    "area under farming": "area_under_cultivation", "area under crops": "area_under_cultivation",
    "land is farmed": "area_under_cultivation", "land is cultivated": "area_under_cultivation",
    "net sown area": "land_use_area", "net area sown": "land_use_area", "cropped area": "land_use_area",
    "area under": "area_cultivated", "area": "area_cultivated", "hectare": "area_cultivated", "क्षेत्रफल": "area_cultivated",
    "production": "production", "produce": "production", "output": "production", "उत्पादन": "production",
    "harvest": "production",
    "yield": "yield", "productivity": "yield", "उपज": "yield",
    "farmers": "farmers_count", "cultivators": "farmers_count", "किसान": "farmers_count",
    "organic farms": "organic_farm_count", "organic": "organic_farm_count",
    "non organic farms": "non_organic_farm_count", "non-organic farms": "non_organic_farm_count",
    "nonorganic": "non_organic_farm_count", "non organic": "non_organic_farm_count", "conventional farms": "non_organic_farm_count",
    "population": "population", "households": "households", "livestock": "livestock_count",
    "poultry": "poultry_count", "fish landed": "fish_landed", "fish catch": "fish_landed",
    "forest": "forest_area", "geographical area": "geographical_area",
    "tractors": "tractor_count", "power tillers": "power_tiller_count", "pump sets": "pump_set_count",
    "kisan credit": "kcc_count", "kcc": "kcc_count", "godowns": "godown_count", "check dams": "check_dam_count",
    "fertilizer": "fertilizer_consumption", "fertiliser": "fertilizer_consumption",
    "seedlings": "seedling_distributed", "vermi": "vermi_bed_count", "depots": "agri_depot_count",
    "land cover": "lulc_area", "lulc": "lulc_area",
    "cost of cultivation": "cost_of_cultivation", "holdings": "holdings_count",
    "scheme outlay": "scheme_outlay", "budget": "scheme_outlay", "expenditure": "scheme_expenditure",
    # everyday wording found with the coverage battery (data/gold/queries_battery.json)
    "farmer": "farmers_count", "farming families": "farmers_count",
    "how big": "geographical_area", "size of": "geographical_area", "biggest island": "geographical_area",
    "largest island": "geographical_area", "smallest island": "geographical_area", "biggest district": "geographical_area",
    "largest district": "geographical_area", "land area": "geographical_area", "total area": "geographical_area",
    "people": "population", "inhabitants": "population", "residents": "population", "populated": "population",
    "cattle": "livestock_count", "cows": "livestock_count", "goats": "livestock_count", "animals": "livestock_count",
    "chickens": "poultry_count", "hens": "poultry_count", "birds": "poultry_count",
    "fish": "fish_landed",
    "seed": "seed_distributed", "seedling": "seedling_distributed", "saplings": "seedling_distributed",
    "planting material": "seedling_distributed",
    "agriculture farms": "agri_farm_count", "agricultural farms": "agri_farm_count", "agri farms": "agri_farm_count",
    "government farms": "agri_farm_count", "department farms": "agri_farm_count",
    "wells": "well_count", "ponds": "pond_count", "farm ponds": "pond_count",
    "power connection": "agri_power_connections", "electricity connection": "agri_power_connections",
    "pesticide": "pesticide_distributed", "manure": "manure_unit_count", "compost units": "manure_unit_count",
    "vermicompost": "vermi_bed_count", "depot": "agri_depot_count", "godown": "godown_count", "warehouse": "godown_count",
    "tractor": "tractor_count", "power tiller": "power_tiller_count", "pump set": "pump_set_count", "pumpset": "pump_set_count",
    "credit card": "kcc_count",
    "spent": "scheme_expenditure", "spending": "scheme_expenditure", "outlay": "scheme_outlay", "allocation": "scheme_outlay",
    "holdings area": "holdings_area", "area of operational holdings": "holdings_area", "area of holdings": "holdings_area",
    "area under holdings": "holdings_area", "area of land holdings": "holdings_area", "operational holdings": "holdings_count",
    "land holdings": "holdings_count",
    "land use": "land_use_area", "land utilisation": "land_use_area", "land utilization": "land_use_area",
    "fallow": "land_use_area", "barren": "land_use_area", "cultivable waste": "land_use_area", "pasture": "land_use_area",
    "grazing land": "land_use_area", "culturable land": "land_use_area", "cultivable land": "land_use_area",
    "area sown more than once": "land_use_area", "total cropped area": "land_use_area", "gross cropped area": "land_use_area",
    "non agricultural use": "land_use_area", "reporting area": "land_use_area",
    "land use land cover": "lulc_area", "land use / land cover": "lulc_area", "satellite": "lulc_area",
    "cost": "retail_price", "dozen": "retail_price", "per kg": "retail_price", "per litre": "retail_price",
    "costly": "retail_price", "pricey": "retail_price",
}
# Word cues that support a measure chosen by the model when no listed synonym matched ("land under coconut").
METRIC_CUES = {
    "area_cultivated": r"\b(land|area|hectares?|ha|acres?|planted|sown|acreage|under)\b",
    "production": r"\b(produc\w*|output|harvest\w*|tonnes?|tons?|grown|grow\w*|crop)\b",
    "yield": r"\b(yield|productivity|per hectare|per ha)\b",
    "retail_price": r"\b(price\w*|cost\w*|rate|expensive|cheap\w*|rupees?|rs|inr|market)\b",
    "cost_of_cultivation": r"\b(cost of cultivation|cultivation cost|cost to grow|input cost)\b",
}
# Everyday words used only when no measure is named explicitly ("has rice farming gone down?").
WEAK_METRIC_WORDS = {"farming": "production", "grown": "production", "grow": "production", "cultivat": "area_cultivated",
                     "how much": "production", "how many farmers": "farmers_count"}
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
        loc = self.alias.setdefault("location", {})
        for a in ("andaman and nicobar", "andaman nicobar", "andaman & nicobar island", "a and n", "the ut",
                  "union territory", "whole ut", "all islands"):
            loc.setdefault(a, {"AN"})
        com = self.alias.get("commodity", {})
        bases: dict[str, set[str]] = {}
        for a, ids in com.items():                # "chicken (dressed)" + "chicken (poultry)" -> "chicken" means both
            if " (" in a and a.isascii():
                bases.setdefault(a.split(" (")[0].strip(), set()).update(ids)
        for b, ids in bases.items():
            if len(b) >= 4 and com.get(b, set()) <= ids:   # 'banana' stays banana; 'chilli' = dry or green chilli
                com[b] = set(com.get(b, set())) | ids
        for a, ids in list(com.items()):          # singular / plural forms: "egg" finds "eggs", "tomatoes" finds "tomato"
            if len(a) < 4 or not a.isascii() or " (" in a:
                continue
            for v in ({a[:-2]} if a.endswith(("oes", "ies")) else set()) | ({a[:-1]} if a.endswith("s") else
                                                                              {a + "s", a + "es" if a.endswith("o") else a + "s"}):
                if len(v) >= 3 and v not in com:
                    com[v] = set(ids)
        self.level = {r["location_id"]: r["level"] for r in conn.execute("SELECT location_id, level FROM location")}
        self.loc_name = {r["location_id"]: r["name"] for r in conn.execute("SELECT location_id, name FROM location")}
        self.com_name = {r["commodity_id"]: r["name"] for r in conn.execute("SELECT commodity_id, name FROM commodity")}
        self.conn = conn
        self.metric_name = {r["metric_id"]: r["name"] for r in conn.execute("SELECT metric_id, name FROM metric")}
        self.unit_symbol = {r["unit_id"]: r["symbol"] for r in conn.execute("SELECT unit_id, symbol FROM unit")}
        self.observed_commodities = {r[0] for r in conn.execute("SELECT DISTINCT commodity_id FROM observation")}
        # measures that never carry an item, and measures that only sometimes do (seedlings: coconut / pineapple / total)
        share = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT metric_id, SUM(commodity_id IS NOT NULL), COUNT(*) FROM observation WHERE validation != 'error' GROUP BY 1")}
        self.item_free = {m for m, (k, n) in share.items() if k == 0}
        self.item_optional = {m for m, (k, n) in share.items() if 0 < k < n}
        self.com_metrics: dict[str, set[str]] = {}
        for r in conn.execute("SELECT DISTINCT commodity_id, metric_id FROM observation WHERE validation != 'error' "
                              "AND commodity_id IS NOT NULL"):
            self.com_metrics.setdefault(r[0], set()).add(r[1])
        self.loc_metrics: dict[str, set[str]] = {}
        for r in conn.execute("SELECT DISTINCT location_id, metric_id FROM observation WHERE validation != 'error'"):
            self.loc_metrics.setdefault(r[0], set()).add(r[1])

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

    def commodities_in(self, q: str) -> list[str]:
        """Every observed item named in q (longest alias first, no overlaps); 'rice' means the paddy crop
        unless the question is about prices."""
        hits, taken, owner = [], [], {}
        for a, i in self.scan("commodity", q):
            if i not in self.observed_commodities or i in hits:
                continue
            span = [m.span() for m in re.finditer(r"(?<![\w])" + re.escape(a) + r"(?![\w])", q)]
            if any(s0 < t1 and t0 < s1 and owner.get((t0, t1)) != a for s0, s1 in span for t0, t1 in taken):
                continue                      # overlaps a longer alias; the same alias may name several items
            taken += span
            owner.update({sp: a for sp in span})
            hits.append((min(x[0] for x in span) if span else 10**6, i))
        hits = [i for _, i in sorted(hits)]          # in the order the question names them
        price_ctx = re.search(r"price|rate|cost|expensive|cheap|per kg|market|retail|₹|rs\.?\b|inr", q)
        if not price_ctx:
            hits = ["paddy" if h == "rice" else h for h in hits]
            if re.search(r"(?<![\w])(rice|chawal|चावल)(?![\w])", q) and "paddy" not in hits:
                hits.insert(0, "paddy")
        return list(dict.fromkeys(hits))

    def commodity_in(self, q: str) -> str | None:
        hits = self.commodities_in(q)
        return hits[0] if hits else None

    def location_in(self, q: str, level_hint: str | None, metric: str | None = None) -> str | None:
        hits = self.scan("location", q)
        if not hits:
            return None
        best_len = len(hits[0][0])
        cands = [i for a, i in hits if len(a) == best_len]
        # 'car nicobar' is a zone, an island and a tehsil: also consider the same name at the other levels, and
        # prefer the one that actually has data for the measure asked about (farmers -> island, paddy -> zone)
        if metric:
            base, family = hits[0][0], list(cands)
            loc_alias = self.alias.get("location", {})
            for suffix in (" island", " (agri zone)", " tehsil", " district"):
                family += [i for i in loc_alias.get(base + suffix, ()) if i not in family]
            with_data = [c for c in family if metric in self.loc_metrics.get(c, ())]
            if with_data:
                cands = with_data
        if level_hint:
            pref = [c for c in cands if self.level.get(c) == level_hint]
            if pref:
                return pref[0]
        order = ["district", "island", "agri_zone", "tehsil", "ut", "market"]
        return sorted(cands, key=lambda c: order.index(self.level[c]) if self.level.get(c) in order else 9)[0]

    def latest_label(self, metric: str, commodity: str | None, location: str | None) -> str | None:
        return T.latest_period(self.conn, metric, commodity, None, location)

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
    if metric is None:
        for k in sorted(WEAK_METRIC_WORDS, key=len, reverse=True):
            if k in q:
                metric = WEAK_METRIC_WORDS[k]
                metric_explicit = True
                break
    commodity = R.commodity_in(q)
    location = R.location_in(q, level, metric) if level and not any(w in q for w in RANK_WORDS) else \
        R.location_in(q, None, metric)
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
                                                     "increase", "decrease", "peak", "बदला", "रुझान", "gone down",
                                                     "gone up", "going down", "going up", "growing", "shrinking",
                                                     "falling", "dropped", "drop", "rising", "history", "over the last",
                                                     "past few", "last few", "years"))):
        intent = "trend"
    elif any(w in q for w in RANK_WORDS) or (level and not (location and R.level.get(location) == level)):
        intent = "rank"
    else:
        intent = "lookup"
    if intent == "rank" and location and R.level.get(location) == level:
        location = None                      # "which island ..." names a level, not one place
    if metric is None:
        metric = "retail_price" if commodity and commodity not in _crop_commodities(R) else "production"
    if metric in NON_COMMODITY or metric in R.item_free:
        commodity = None
    if intent in ("trend", "lookup", "provenance", "compare_sources") and not location:
        location = "MKT_AN" if metric in PRICE_METRICS else "AN"
    if metric in PRICE_METRICS and intent != "nearby":
        location = "MKT_AN"
    if location == "AN_ANDAMAN" and metric != "lulc_area":
        location = "AN"          # "Andaman" alone means the territory; the LULC tables alone report the two districts together
    p = Plan(intent=intent, metric=metric, commodity=commodity, location=location, level=level,
             confident=metric_explicit and (commodity is not None or metric in NON_COMMODITY
                                            or metric in R.item_free or metric in R.item_optional))
    if intent == "trend":
        p.start, p.end = (periods[0], periods[-1]) if len(periods) >= 2 else (periods[0] if periods else None, None)
    else:
        p.period = periods[0] if periods else None
    apply_relative_time(p, q, R)
    if p.metric in PRICE_METRICS and p.period and re.fullmatch(r"(19|20)\d\d", p.period):
        yr = p.period                         # prices are monthly: a bare year means January-December of that year
        p.intent = "trend" if p.intent in ("lookup", "rank") else p.intent
        if p.intent == "trend":
            p.period, p.start, p.end = None, f"January {yr}", f"December {yr}"
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


def apply_relative_time(p: Plan, q: str, R: Resolver) -> None:
    """'last year', 'this year', 'last 3 years', 'latest', 'recent' -> concrete periods from the data."""
    for w, d in (("two", "2"), ("three", "3"), ("four", "4"), ("five", "5"), ("six", "6"), ("couple of", "2")):
        q = re.sub(rf"\b{w}\s+(years?)\b", rf"{d} \1", q)
    m = RELATIVE_TIME.search(q)
    if not m or p.period or p.start:
        return
    latest = R.latest_label(p.metric, p.commodity, p.location)
    if not latest:
        return
    yr = int(re.search(r"(19|20)\d\d", latest).group(0))
    monthly = p.metric in PRICE_METRICS
    if m.group(2):                                        # last N years
        n_ = int(m.group(2))
        p.intent = "trend" if p.intent in ("lookup", "provenance") else p.intent
        p.start = f"January {yr - n_ + 1}" if monthly else f"{yr - n_ + 1}-{str(yr - n_ + 2)[-2:]}"
    elif re.search(r"last year|previous year|this year", m.group(0), re.I) and monthly:
        p.intent = "trend" if p.intent in ("lookup",) else p.intent
        if p.intent == "trend":
            p.start, p.end = f"January {yr}", f"December {yr}"
        else:
            p.period = latest
    elif p.intent != "trend":
        p.period = latest


def ground(p: Plan, q: str, R: Resolver) -> tuple[Plan | None, str]:
    """Keep only what the question supports. Returns (plan, note) or (None, reason) when nothing grounded is left."""
    qn = _norm(q)
    named = R.commodities_in(qn)
    first_word = (_norm(R.metric_name.get(p.metric, "")).split() or [""])[0]
    metric_named = any(re.search(r"(?<![\w])" + re.escape(k), qn) for k in list(METRIC_SYNONYMS) + list(WEAK_METRIC_WORDS)) or \
        (len(first_word) > 3 and first_word in qn)
    place_named = R.location_in(qn, None) is not None or any(re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", qn)
                                                            for w in LEVEL_WORDS) or \
        re.search(r"\b(ut|union territory|a&n|andaman|nicobar|islands?|port blair)\b", qn) is not None
    if p.commodity and p.commodity not in named:
        p.commodity = named[0] if named else None
    if p.commodity and p.metric and p.metric not in R.com_metrics.get(p.commodity, ()):
        # 'chilli' is both dry chilli (crop tables) and green chilli (price tables): use the one with this measure
        alt = [c for c in named if p.metric in R.com_metrics.get(c, ())]
        if alt:
            p.commodity = alt[0]
    if not metric_named and not named and not place_named:
        return None, "nothing in the question names a measure, crop or place"
    if p.intent == "nearby" and not metric_named and not named:
        p.metric, p.commodity = None, None      # "islands within 30 km of X": places only
        return p, ""
    if not metric_named and not named:
        # "which zone is the best / has the most crops": a place or level but no measure and no item. Any measure
        # here would be a guess (the model picked geographical area and total cultivated area), so ask instead.
        hits = R.scan("location", qn)
        if hits and not (p.level and p.intent == "rank"):
            # a named place: every level that carries this name (Car Nicobar = zone, island and tehsil)
            base = hits[0][0]
            locs = {i for a, ids in R.alias.get("location", {}).items() if a == base or a.startswith(base + " ")
                    for i in ids}
            where = R.loc_name.get(sorted(locs, key=lambda x: -len(R.loc_metrics.get(x, ())))[0], base)
        else:
            lvl = p.level or (R.level.get(p.location) if p.location else None)
            locs = {loc for loc, v in R.level.items() if v == lvl} if lvl else set()
            where = {"agri_zone": "agri zones", "district": "districts", "island": "islands"}.get(lvl, "the UT")
            if not locs:
                locs = {"AN"}
        have = sorted({R.metric_name.get(m, m) for loc in locs for m in R.loc_metrics.get(loc, ())} - {None})
        return None, ("ask: " + f"Which measure do you mean? Please name a measure or a crop. For {where} the knowledge base has: "
                      + "; ".join(have[:14]) + ". For example: \"which zone produces the most paddy?\", "
                      "\"which island has the most farmers?\", \"which district has the most area under cultivation?\"")
    cue = METRIC_CUES.get(p.metric)
    if not metric_named and named and cue and re.search(cue, qn):
        metric_named = True                     # the model's measure is supported by a word in the question
    if not metric_named and named:
        # an item but no measure ("which zone is best for paddy"): use the item's main measure, never a model guess
        com = p.commodity or named[0]
        has = R.com_metrics.get(com, set())
        price_ctx = re.search(r"price|rate|cost|expensive|cheap|costly|market|retail|₹|\brs\b|inr", qn)
        p.metric = ("retail_price" if (price_ctx or "production" not in has) and "retail_price" in has else
                    "production" if "production" in has else sorted(has)[0] if has else p.metric)
        p.commodity = com
    if p.commodity is None and p.metric == "area_cultivated" and not named:
        # no crop named: "area under agriculture / farmland" = total cultivated land; plain "largest area" = size
        agri = re.search(r"agri|farm|cultivat|crop|sown|grow|plant|under|cropped|tilled|हेक्टेयर|खेती", qn)
        p.metric = "area_under_cultivation" if agri else "geographical_area"
    if p.metric in R.item_free:
        p.commodity = None
    if p.metric in PRICE_METRICS and p.intent == "rank" and not p.level:
        p.intent = "trend"                      # one market only: "when was onion most expensive" is a time question
        p.start = p.start or p.period
        p.period = None
    if p.location and p.metric and p.metric not in R.loc_metrics.get(p.location, ()):
        alt = R.location_in(qn, p.level, p.metric)   # same name at a level that has this measure
        if alt and p.metric in R.loc_metrics.get(alt, ()):
            p.location = alt
    if p.commodity is None and p.metric not in NON_COMMODITY and p.metric not in R.item_free \
            and p.metric not in R.item_optional and p.metric != "lulc_area":
        if named:
            p.commodity = named[0]
        else:
            return None, "the question does not say which crop or item"
    if p.location and p.location not in ("AN", "MKT_AN") and R.location_in(qn, p.level) is None:
        p.location = "MKT_AN" if p.metric in PRICE_METRICS else "AN"
    if p.location == "AN_ANDAMAN" and p.metric != "lulc_area":
        p.location = "AN"
    return p, ""


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
                gp, why = ground(rp, question, self.R)
                return (gp, "rules", "") if gp else (None, "rules", f"refused: {why}")
            raw, text = model_plan(question, self.llm, self.few_shot)
            p = plan_from_model(raw, self.R, question) if raw else None
            if p:
                apply_relative_time(p, _norm(question), self.R)
                gp, why = ground(p, question, self.R)
                return (gp, "rules->model", text) if gp else (None, "rules->model", f"refused: {why} | {text}")
            gp, why = ground(rp, question, self.R)
            return (gp, "rules->model(invalid)->rules", text) if gp else (None, "rules->model(invalid)", f"refused: {why}")
        use_model = self.planner in ("auto", "model") and self.llm is not None and self.llm.enabled
        if use_model:
            raw, text = model_plan(question, self.llm, self.few_shot)
            p = plan_from_model(raw, self.R, question) if raw else None
            if p:
                return p, "model", text
            if self.planner == "model":
                return None, "model(invalid)", text
            return rule_plan(question, self.R), "model->rules", text
        gp, why = ground(rule_plan(question, self.R), question, self.R)
        return (gp, "rules", "") if gp else (None, "rules", f"refused: {why}")

    # ---------------------------------------------------------- fallbacks when the exact request has no data
    def availability(self, metric: str | None, commodity: str | None) -> dict:
        """Which levels, places and periods hold this measure (used to explain or redirect an empty answer)."""
        if not metric:
            return {"levels": {}, "periods": []}
        rows = self.conn.execute(
            "SELECT l.level, COUNT(DISTINCT o.location_id) n FROM observation o JOIN location l USING(location_id) "
            "WHERE o.metric_id=? AND o.commodity_id IS ? AND o.value IS NOT NULL AND o.validation != 'error' "
            "GROUP BY l.level", (metric, commodity)).fetchall()
        per = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT period_label FROM observation WHERE metric_id=? AND commodity_id IS ? AND value IS NOT NULL "
            "AND validation != 'error' ORDER BY period_start", (metric, commodity))]
        return {"levels": {r[0]: r[1] for r in rows}, "periods": per}

    def _lvl(self, level: str) -> str:
        return {"agri_zone": "agri zone", "ut": "UT"}.get(level, level)

    def run(self, p: Plan) -> tuple[T.ToolResult, Plan, str]:
        """Execute the plan; when it returns nothing, try the closest request that the data can answer and say so.
        Order: another level (rank), the parent place (lookup / trend), production for yield, the latest period."""
        res = self.execute(p)
        if res.rows or p.intent == "nearby":
            return res, p, ""
        R, what = self.R, self.R.metric_name.get(p.metric, p.metric or "")
        av = self.availability(p.metric, p.commodity)
        # yield is printed only for the UT (2023-24): rank / compare places on production instead
        if p.metric == "yield" and p.intent == "rank" and set(av["levels"]) <= {"ut"}:
            q = Plan(**{**asdict(p), "metric": "production"})
            r2, q2, n2 = self.run(q)
            if r2.rows:
                return r2, q2, ("Yield is published only as a UT figure, so places cannot be compared on yield; "
                                "ranking by production instead. " + n2).strip()
        if p.intent == "rank":
            sub = {k: v for k, v in av["levels"].items() if k not in ("ut", "market") and v >= 2}
            if p.level and p.level not in sub and sub:
                pref = {"agri_zone": ["district", "island"], "island": ["district", "agri_zone"],
                        "tehsil": ["island", "district", "agri_zone"], "district": ["agri_zone", "island"]}
                new = next((x for x in pref.get(p.level, []) if x in sub), max(sub, key=sub.get))
                q = Plan(**{**asdict(p), "level": new})
                r2 = self.execute(q)
                if r2.rows:
                    return r2, q, (f"{what} is not published by {self._lvl(p.level)}; the sources give it by "
                                   f"{', '.join(self._lvl(x) for x in sub)}. Showing it by {self._lvl(new)}.")
            if p.period and av["periods"] and p.period not in av["periods"]:
                q = Plan(**{**asdict(p), "period": None})
                r2, q2, n2 = self.run(q)
                if r2.rows:
                    return r2, q2, (f"No {what} figure for {p.period}; the sources cover {av['periods'][0]} to "
                                    f"{av['periods'][-1]}. Showing the latest. " + n2).strip()
        if p.intent in ("lookup", "provenance", "trend", "compare_sources") and p.location:
            # the place has no such figure: use the place it belongs to (zone -> district -> UT)
            loc, seen = p.location, set()
            while loc and loc not in seen:
                seen.add(loc)
                parent = self.conn.execute("SELECT parent_id FROM location WHERE location_id=?", (loc,)).fetchone()
                loc = parent[0] if parent else None
                if loc and p.metric in R.loc_metrics.get(loc, ()):
                    for per in ([p.period, None] if p.period else [None]):
                        q = Plan(**{**asdict(p), "location": loc, "period": per})
                        r2 = self.execute(q)
                        if r2.rows:
                            return r2, q, (f"{what} is not published for {R.loc_name.get(p.location, p.location)}"
                                           + (f" in {p.period}" if p.period and per is None else "")
                                           + f"; showing {R.loc_name.get(loc, loc)}, which contains it"
                                           + (", latest available year" if p.period and per is None else "") + ".")
            if p.intent in ("lookup", "provenance") and p.period and av["periods"]:
                q = Plan(**{**asdict(p), "period": None})
                r2 = self.execute(q)
                if r2.rows:
                    return r2, q, (f"No {what} figure for {p.period} here; the sources cover {av['periods'][0]} to "
                                   f"{av['periods'][-1]}. Showing the latest.")
        # published only for smaller places (islands): add them up for the place asked about, and say so
        if p.intent in ("lookup", "provenance", "trend", "compare_sources") and p.location and p.metric:
            r2, note = self.rollup(p)
            if r2 is not None:
                return r2, Plan(**{**asdict(p), "intent": "rank", "level": r2.summary["level"], "location": None}), note
        # published only for the UT: a ranking by district / zone / island cannot be made; give the UT figure
        if p.intent == "rank" and set(av["levels"]) <= {"ut"} and av["levels"]:
            q = Plan(**{**asdict(p), "intent": "lookup", "location": "AN", "level": None})
            r2 = self.execute(q)
            if r2.rows:
                return r2, q, (f"{what} is published only for the whole UT, not by "
                               f"{self._lvl(p.level or 'district')}; here is the UT figure.")
        return res, p, ""

    def descendants(self, loc: str) -> set[str]:
        kids = {r[0]: r[1] for r in self.conn.execute("SELECT location_id, parent_id FROM location")}
        out, frontier = set(), {loc}
        while frontier:
            frontier = {k for k, par in kids.items() if par in frontier} - out
            out |= frontier
        return out

    def rollup(self, p: Plan) -> tuple[T.ToolResult | None, str]:
        """Sum the smaller places inside p.location that report the measure (e.g. livestock per island -> UT)."""
        if p.metric in PRICE_METRICS or p.metric == "yield" or p.metric == "cost_of_cultivation":
            return None, ""                       # not additive
        av = self.availability(p.metric, p.commodity)
        name = self.R.loc_name.get(p.location, p.location)
        base = re.sub(r"\s*\((agri zone)\)|\s+(island|tehsil|district)$", "", name.lower()).strip()
        namesakes = [p.location] + sorted({i for a, ids in self.R.alias.get("location", {}).items()
                                           if a in (base, base + " tehsil", base + " island", base + " district")
                                           for i in ids} - {p.location})
        for place in namesakes:
            inside = self.descendants(place)
            if not inside:
                continue
            for level in ("district", "agri_zone", "island"):
                if level not in av["levels"]:
                    continue
                rows, res = [], None
                for per in ([p.period] if p.period else []) + [x for x in reversed(av["periods"]) if x != p.period]:
                    res = T.rank_locations(self.conn, p.metric, p.commodity, per, level, top_k=100, order="desc")
                    rows = [r for r in res.rows if r["location_id"] in inside]
                    if rows:
                        break
                if rows:
                    return self._rollup_result(p, place, level, res, rows)
        return None, ""

    def _rollup_result(self, p: Plan, place: str, level: str, res: T.ToolResult,
                       rows: list[dict]) -> tuple[T.ToolResult, str]:
        """Rows of the smaller places inside `place`, with their total and an explicit note."""
        inside = self.descendants(place)
        total = sum(r["value_std"] for r in rows)
        for r in rows:
            r["share_pct"] = round(100 * r["value_std"] / total, 1) if total else None
        res.rows, res.summary["n_locations"] = rows, len(rows)
        n_all = sum(1 for loc in inside if self.R.level.get(loc) == level)
        unit = self.R.unit_symbol.get(rows[0].get("unit_std"), rows[0].get("unit_std") or "")
        unit = {"MT (tonne)": "t", "number": "", "count": ""}.get(unit, unit)
        what = self.R.metric_name.get(p.metric, p.metric)
        name = self.R.loc_name.get(place, place)
        asked = self.R.loc_name.get(p.location, p.location)
        note = ((f"{asked} has no such figure; using {name}. " if place != p.location else "")
                + f"{what} is not published as one figure for {name}; it is published by {self._lvl(level)}. "
                f"Total of the {len(rows)} {self._lvl(level)}s that report it ({res.summary['period']}): "
                f"{_fmt(total)} {unit}".rstrip() + "."
                + (f" {n_all - len(rows)} other {self._lvl(level)}s in {name} report no figure and are not included."
                   if n_all > len(rows) else ""))
        if p.intent == "trend":
            note += " Only this period can be added up reliably, so no trend is computed."
        if p.period and res.summary.get("period") != p.period:
            note += f" No figure for {p.period}; this is the latest year with one."
        return res, note

    def explain_empty(self, p: Plan) -> str:
        """Say what the knowledge base does hold for this measure, so 'No data' is never a dead end."""
        av = self.availability(p.metric, p.commodity)
        if not av["levels"]:
            if p.commodity and p.metric:
                has = sorted(self.R.metric_name.get(m, m) for m in self.R.com_metrics.get(p.commodity, ()))
                return (f" The sources do not report this measure for {self.R.com_name.get(p.commodity, p.commodity)}"
                        + (f"; they do report: {', '.join(has)}." if has else "."))
            return ""
        lv = ", ".join(f"{self._lvl(k)} ({v} place{'s' if v > 1 else ''})" for k, v in av["levels"].items())
        return f" It is published by: {lv}, for {av['periods'][0]} to {av['periods'][-1]}."

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
        sc = classify(question, len([c for c in self.R.commodities_in(_norm(question)) if not c.startswith("agg_")]))
        if sc.kind in ("chitchat", "not_in_kb", "rank_items"):
            ans = Answer(question, "out_of_scope", f"scope:{sc.kind}", {"intent": "out_of_scope"}, "none", {}, "", sc.message)
            ans.latency_s, ans.query_id = round(time.time() - t0, 2), qid
            self._log(ans, "")
            return ans
        p, planner, raw = self.plan(question)
        items = self.R.commodities_in(_norm(question))
        if p is not None and p.metric:          # keep only the named items that have this measure at all
            items = [i for i in items if p.metric in self.R.com_metrics.get(i, ())] or items
        if p is not None and len(items) >= 2 and p.intent in ("lookup", "trend", "provenance") and p.metric not in NON_COMMODITY:
            return self._ask_each(question, p, planner, raw, items[:3], t0, qid, sc)
        if p is None and raw.startswith("refused"):
            reason = raw.split('|')[0].replace('refused: ', '').strip()
            msg = reason[5:] if reason.startswith("ask: ") else f"I could not match this to the data ({reason}). " + HELP
            ans = Answer(question, "out_of_scope", planner, {"intent": "out_of_scope"}, "none", {}, "", msg)
        elif p is None:
            ans = Answer(question, "unknown", planner, {}, "", {}, "", "Sorry, I could not turn this question into a "
                         "query. Try naming a crop or metric, a place and a year.", error=f"invalid plan: {raw[:200]}")
        else:
            try:
                res, p, note = self.run(p)
                focus_parts(res, question)
                text, cites = compose(p, res, self.R)
                if not res.rows:
                    text += self.explain_empty(p)
                elif note:
                    text = "Note: " + note + "\n" + text
                if sc.kind == "why":
                    text = sc.message + "\n" + text
                ans = Answer(question, INTENTS[p.intent], planner, asdict(p), res.tool, res.args, res.sql.strip(), text,
                             res.rows, res.summary, cites)
            except Exception as e:  # noqa: BLE001 - reported to the user, logged
                ans = Answer(question, INTENTS[p.intent], planner, asdict(p), "", {}, "", f"Query failed: {e}", error=str(e))
        ans.latency_s = round(time.time() - t0, 2)
        ans.query_id = qid
        self._log(ans, raw)
        return ans

    def _ask_each(self, question, p, planner, raw, items, t0, qid, sc) -> Answer:
        """Side-by-side answer when the question names two or three items (e.g. 'compare paddy and arecanut area')."""
        texts, rows, cites = [], [], []
        for it in items:
            q = Plan(**{**asdict(p), "commodity": it})
            try:
                res, q, note = self.run(q)
                t, c = compose(q, res, self.R)
                if not res.rows:
                    t += self.explain_empty(q)
                elif note:
                    t = "Note: " + note + "\n" + t
                texts.append(t)
                rows += res.rows
                cites += c
            except Exception as e:  # noqa: BLE001
                texts.append(f"{it}: query failed ({e})")
        text = ("\n\n".join(texts) if sc.kind != "why" else sc.message + "\n" + "\n\n".join(texts))
        ans = Answer(question, INTENTS[p.intent], planner + "+each", asdict(p), "per_item", {"items": items}, "", text,
                     rows, {}, cites)
        ans.latency_s, ans.query_id = round(time.time() - t0, 2), qid
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


_PART_STOP = {"land", "area", "the", "and", "other", "than", "not", "for", "total", "under", "of", "in", "what", "how",
              "much", "is", "was", "are", "a", "by", "with"}


def focus_parts(res: T.ToolResult, question: str) -> None:
    """A breakdown answer ('fallow land' in the land-utilisation table) lists the parts the question names first."""
    if not res.rows or "part" not in res.rows[0]:
        return
    words = {w for w in re.findall(r"[a-z]+", question.lower()) if len(w) > 3 and w not in _PART_STOP}
    hit = [r for r in res.rows if words & set(re.findall(r"[a-z]+", r["part"].lower()))]
    if hit:
        res.rows = hit + [r for r in res.rows if r not in hit]


def _disagree(rows: list[dict], unit: str, by: str, limit: int = 4) -> list[str]:
    """One line per fact whose printed sources disagree: which value was used and what else was printed."""
    out = []
    for r in rows:
        alts = r.get("alternatives") or []
        if not alts:
            continue
        others = ", ".join(f"{_fmt(a['value_std'])} [{a['document_id']} p{a['page']}]" for a in alts[:3])
        how = f" ({r['chosen_by']})" if r.get("chosen_by") else ""
        out.append(f"  ⚠ Sources disagree for {r[by]}: used {_fmt(r['value_std'])} {unit} "
                   f"[{r['document_id']} p{r['page']}]{how}; also printed {others}.")
    if len(out) > limit:
        out = out[:limit] + [f"  ⚠ ... and {len(out) - limit} more where the printed sources disagree."]
    return out


def compose(p: Plan, res: T.ToolResult, R: Resolver) -> tuple[str, list[dict]]:
    rows = res.rows
    what = R.metric_name.get(p.metric, p.metric or "") + (f" of {R.com_name.get(p.commodity, p.commodity)}" if p.commodity else "")
    if not rows:
        return (f"No data in the knowledge base for {what}"
                + (f" by {p.level.replace('agri_zone', 'agri zone')}" if p.intent == "rank" and p.level else "")
                + (f" at {R.loc_name.get(p.location, p.location)}" if p.location and p.intent != "rank" else "")
                + (f" in {res.args.get('period') or p.period}" if (res.args.get('period') or p.period) else "") + "."), []
    for r in rows:                      # show every number in the metric's standard unit (citation keeps the printed text)
        if r.get("value_std") is not None and r.get("unit_std"):
            r["value"], r["unit_id"] = r["value_std"], r["unit_std"]
    unit = R.unit_symbol.get(rows[0].get("unit_id"), rows[0].get("unit_id") or "")
    unit = {"MT (tonne)": "t", "number": "", "count": ""}.get(unit, unit)
    if res.tool == "rank_locations":
        lvl = res.summary["level"].replace("agri_zone", "agri zone")
        head = rows[0]
        lines = [f"{what} by {lvl}, {res.summary['period']} ({res.summary['n_locations']} {lvl}s with data): "
                 f"{head['location']} is {'highest' if p.order == 'desc' else 'lowest'} with {_fmt(head['value'])} {unit}"
                 + (f" ({head['share_pct']}% of the total)" if head.get("share_pct") is not None else "") + f" {_cite_txt(head)}."]
        lines += [f"  {i}. {r['location']}: {_fmt(r['value'])} {unit} {_cite_txt(r)}" for i, r in enumerate(rows, 1)]
        if res.summary.get("part"):
            lines.insert(0, f"(No single figure is printed; this ranks the {res.summary['part_kind']} "
                            f"'{res.summary['part']}'" + (f"; also printed: {', '.join(res.summary['other_parts'][:5])}"
                                                          if res.summary.get("other_parts") else "") + ".)")
        lines += _disagree(rows, unit, "location")
        return "\n".join(lines), [_cite(r) for r in rows]
    if res.tool == "time_series":
        s = res.summary
        loc = R.loc_name.get(p.location, p.location)
        lines = [f"{what}, {loc}: {_fmt(s['first'][1])} {unit} in {s['first'][0]} -> {_fmt(s['last'][1])} {unit} in "
                 f"{s['last'][0]} ({(format(s['change_pct'], '+') + '%') if s.get('change_pct') is not None else 'change n/a'} over {s['n_periods']} periods). Peak {_fmt(s['peak'][1])} in "
                 f"{s['peak'][0]}; low {_fmt(s['low'][1])} in {s['low'][0]}. Sources: {', '.join(s['documents'])}."]
        lines += [f"  {r['period_label']}: {_fmt(r['value'])} {unit} {_cite_txt(r)}" for r in rows]
        if s.get("part"):
            lines.insert(0, f"(No single figure is printed; the series below is the {s['part_kind']} '{s['part']}'.)")
            for k, v in list(s.get("other_parts", {}).items())[:6]:
                lines.append(f"  Also printed, {s['part_kind']} '{k}': {_fmt(v['first'][1])} in {v['first'][0]} -> "
                             f"{_fmt(v['last'][1])} in {v['last'][0]} ({v['n']} periods).")
        lines += _disagree(rows, unit, "period_label")
        return "\n".join(lines), [_cite(r) for r in rows]
    if res.tool == "trace_value" and res.summary.get("breakdown"):
        r0 = rows[0]
        loc = R.loc_name.get(r0["location_id"], r0["location_id"])
        seen, parts = set(), []
        for r in rows:
            key = (r["document_id"], r["part"])
            if key in seen:
                continue
            seen.add(key)
            u = R.unit_symbol.get(r.get("unit_id"), r.get("unit_id") or "")
            u = {"MT (tonne)": "t", "number": "", "count": ""}.get(u, u)
            parts.append(f"{r['part']}: {_fmt(r['value'])} {u}".rstrip() + f" {_cite_txt(r)}")
        kind = ("printed only by variety (no single figure)" if res.summary.get("part_kind") == "variety"
                else "reported only as a breakdown (no total row)")
        return (f"{what}, {loc}, {r0['period_label']}: {kind}: " + "; ".join(parts[:10]) + "."), [_cite(r) for r in rows]
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
            vals = [r["value"] for r in rows]
            if max(vals) - min(vals) > T.CONFLICT_PCT / 100 * max(abs(v) for v in vals):
                why = (f"the value shown is the one {res.summary['chosen_by']}" if res.summary.get("chosen_by")
                       else "the value shown comes from the newest publication")
                lines.append(f"  ⚠ These printed values disagree (from {_fmt(min(vals))} to {_fmt(max(vals))} {unit}); "
                             f"{why}.")
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
                 f"({rows[0]['period_label']})"
                 + (f", reported for {len(rows)} of them" if len(rows) < s["n_within_radius"] else "") + ":"]
        lines += [f"  {r['location']} ({r['distance_km']} km): {_fmt(r['value'])} {unit} {_cite_txt(r)}" for r in rows]
        return "\n".join(lines), [_cite(r) for r in rows]
    return json.dumps(rows[:20], default=str), []
