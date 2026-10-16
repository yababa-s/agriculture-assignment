"""G4 island profile agent: agriculture facts from DES 'Island-wise Statistical Outline'.

Pages hold one or more island profiles written as two interleaved columns of
'Key-Value' prose. Decisions:
  rule  : segment pages into island blocks (gazetteer match + 'Area (sq. km.)' line)
  rule  : keep only lines that mention agriculture/allied keywords (cuts tokens ~70%)
  model : extract {metric, value, unit, qualifier, evidence} from the block
  rule  : groundedness gate - evidence must occur in the block and contain the value,
          metric must be in the catalogue; failures are retried once with feedback,
          then the deterministic teacher extractor fills the gaps.
The teacher extractor (regexes below) is also what generated silver training labels
for the LoRA adapter from the 2022-23 and 2023-24 documents only.
"""
from __future__ import annotations

import re

from agri.agents.base import AgentContext, AgentResult, BaseAgent, make_record
from agri.tools.parsing import parse_period
from agri.tools.pdf_tools import page_text_unicode, page_texts

CATALOGUE = {
    "geographical_area": ("sq_km", "Area (sq. km.) of the island"),
    "forest_area": ("sq_km", "Area under forest (sq.km)"),
    "population": ("persons", "Population (2011 Census) total"),
    "households": ("count", "Households"),
    "area_under_cultivation": ("sq_km", "Agriculture: Area under Cultivation; unit sq_km or ha as printed"),
    "farmers_count": ("count", "Farmers"),
    "agri_depot_count": ("count", "Agricultural Depot"),
    "agri_farm_count": ("count", "Agriculture/Agricultural Farm (not organic)"),
    "organic_farm_count": ("count", "Organic Farm"),
    "non_organic_farm_count": ("count", "Non Organic Farm"),
    "check_dam_count": ("count", "Check dam"),
    "godown_count": ("count", "Godown on the agriculture line (next to Check dam / Main store), NOT civil-supplies godown"),
    "vermi_bed_count": ("count", "Vermin/Vermi Bed"),
    "manure_unit_count": ("count", "Manure Selling Unit"),
    "seedling_distributed": ("count", "Distribution: Seedling (in No.)"),
    "fertilizer_consumption": ("mt", "Fertilizer(MT); qualifier = organic_vermicompost | nitrogenous | phosphatic | potassic"),
    "livestock_count": ("count", "Livestock (20th Livestock Census)"),
    "poultry_count": ("count", "Poultry count (not hatchery)"),
    "fish_landed": ("mt", "Fish Landed (MT); qualifier = freshwater | marine"),
    "agri_power_connections": ("count", "Electricity connections: Agriculture"),
}
KEYWORDS = re.compile(r"agricultur|farmer|fertili|nitrogen|phosp|potass|livestock|poultry|fish landed|seedling|vermi|organic|"
                      r"check dam|manure|area \(sq|area under|population\(|population \(|households|street light|connections", re.I)

_N = r"(\.?\d[\d,]*(?:\.\d+)?|NIL|Nil|nil)"
_AGRI_LINE = re.compile(r"check\s*dam|main\s*store|manure|farmers?|vermi|seedling|agricultur", re.I)
TEACHER = [
    ("geographical_area", None, re.compile(r"^Area \(sq\.?\s?km\.?\)\s*" + _N, re.M)),
    ("forest_area", None, re.compile(r"Area under forest\s*\(?sq\.?\s?km\)?\s*" + _N)),
    ("population", None, re.compile(r"Population\s*\(2011 Census\)\s*:\s*" + _N)),
    ("households", None, re.compile(r"Households\s*[-–:]\s*" + _N)),
    ("area_under_cultivation", None, re.compile(r"Area under Cultivation\s*\((?P<u>[^)]*)\)\s*[-–:]*\s*" + _N)),
    ("farmers_count", None, re.compile(r"Farmers?\s*[-–:]\s*" + _N)),
    ("agri_depot_count", None, re.compile(r"Agricultur\w*\s+Depot\.?\s*[-–:]\s*" + _N, re.I)),
    ("agri_farm_count", None, re.compile(r"Agricultur\w*\s+Farm\s*[-–:]\s*" + _N, re.I)),
    ("non_organic_farm_count", None, re.compile(r"Non\s*[-–]?\s*Organic\s+Farm\s*[-–:]\s*" + _N, re.I)),
    ("organic_farm_count", None, re.compile(r"(?<![Nn]on )(?<![Nn]on-)(?<![Nn]on –)(?<![Nn]on)(?<!–)Organic\s+Farm\s*[-–:]\s*" + _N)),
    ("check_dam_count", None, re.compile(r"Check[\s-]*dam\s*[-–:]\s*" + _N, re.I)),
    ("godown_count", None, None),  # line-based, see _godown
    ("vermi_bed_count", None, re.compile(r"Vermi\w*\s+Bed\s*[-–:]\s*" + _N, re.I)),
    ("manure_unit_count", None, re.compile(r"Manure\s+Selling\s+Unit\s*[-–:]\s*" + _N, re.I)),
    ("seedling_distributed", None, re.compile(r"Seedlings?[^-–:\n]{0,26}[-–:]\s*" + _N, re.I)),
    ("fertilizer_consumption", "organic_vermicompost", re.compile(r"vermi\w*\s*compost\s*[-–:]\s*" + _N, re.I)),
    ("fertilizer_consumption", "nitrogenous", re.compile(r"Nitrogenous\s*(?:\(MT\))?\s*[-–:]\s*" + _N, re.I)),
    ("fertilizer_consumption", "phosphatic", re.compile(r"Phos\w*\s*[-–:]\s*" + _N, re.I)),
    ("fertilizer_consumption", "potassic", re.compile(r"Potassic\s*[-–:]\s*" + _N, re.I)),
    ("livestock_count", None, re.compile(r"Livestock\s*[-–:]\s*" + _N, re.I)),
    ("poultry_count", None, re.compile(r"Poultry\s*[-–:]\s*" + _N, re.I)),
    ("fish_landed", "freshwater", re.compile(r"Fish Landed\s*\(MT\)\s*:[^\n]*?Fresh\s*water\s*[-–:]\s*" + _N, re.I)),
    ("fish_landed", "marine", re.compile(r"Fish Landed\s*\(MT\)\s*:[^\n]*?Marine\s*[-–:]\s*" + _N, re.I)),
    ("agri_power_connections", None, re.compile(r"(?:(?:Commercial|Street Light|Domestic)\s*[-–:]\s*\d+\s+Agriculture\s*[-–:]\s*" + _N
                                                + r")|(?:^\s*Agriculture\s*[-–:]\s*" + _N + r"\s+Industrial)", re.I | re.M)),
]


def _godown(block: str):
    """Agriculture-department godown: a 'Godown-N' on a line that is about agriculture (not civil supplies/relief)."""
    for line in block.splitlines():
        m = re.search(r"(?<!Relief )Godown\s*[-–:]\s*" + _N, line, re.I)
        if m and "capacity" not in line.lower() and _AGRI_LINE.search(line):
            return m
    return None


def teacher_extract(block: str) -> list[dict]:
    """Deterministic reference extractor (also the no-LLM fallback)."""
    out = []
    for metric, qual, pat in TEACHER:
        m = _godown(block) if pat is None else pat.search(block)
        if not m:
            continue
        raw = next(g for g in reversed(m.groups()) if g is not None)
        unit = CATALOGUE[metric][0]
        if metric == "area_under_cultivation" and "hect" in (m.groupdict().get("u") or "").lower():
            unit = "ha"
        out.append({"metric": metric, "value": None if raw.lower() == "nil" else float(raw.replace(",", "")),
                    "raw": raw, "unit": unit, "qualifier": qual, "evidence": " ".join(m.group(0).split())})
    return out


def segment_islands(text: str, island_names: dict[str, str]) -> list[tuple[str, str]]:
    """Split a page into (location_id, block_text). A header is a line ending in an island alias
    followed within 3 lines by 'Area (sq. km.)'."""
    lines = text.splitlines()
    starts = []
    for i, line in enumerate(lines):
        low = " ".join(line.lower().split())
        if not low or len(low) > 80:
            continue
        nxt = " ".join(lines[i + 1:i + 4]).lower()
        if "area (sq" not in nxt:
            continue
        best = None
        for alias, lid in island_names.items():
            hit = low.endswith(alias) or low.endswith(alias + " island")
            if hit and (best is None or len(alias) > len(best[0])):
                best = (alias, lid)
        if best:
            starts.append((i, best[1]))
    blocks = []
    for k, (i, lid) in enumerate(starts):
        j = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        blocks.append((lid, "\n".join(lines[i:j])))
    return blocks


SYSTEM = (
    "You extract agriculture statistics from an island profile of the Andaman & Nicobar Islands. "
    "Return a JSON list only. Each item: {\"metric\": <metric id from the catalogue>, \"value\": <number or null if NIL>, "
    "\"unit\": <unit id>, \"qualifier\": <string or null>, \"evidence\": <exact text span copied from the profile>}. "
    "Copy numbers exactly as printed. Skip anything not in the catalogue (schools, police, tourism, etc.)."
)


def build_prompt(block: str) -> str:
    cat = "\n".join(f"- {k} [{u}]: {d}" for k, (u, d) in CATALOGUE.items())
    return f"Metric catalogue:\n{cat}\n\nIsland profile:\n{block}"


def relevant_lines(block: str) -> str:
    lines = block.splitlines()
    keep = [lines[0]] + [ln for ln in lines[1:] if KEYWORDS.search(ln)]
    # 'Area (sq. km.)' value sits on the next line in this layout
    out = []
    for i, ln in enumerate(lines):
        if ln in keep or (i > 0 and re.match(r"^\s*Area (under forest|\(sq)", lines[i - 1])):
            out.append(" ".join(ln.split()))
    return "\n".join(x for x in out if x)


def raw_from_evidence(evidence: str, value: float | None) -> str:
    """The number exactly as printed: the token in the (verified) evidence span equal to the value."""
    if value is None:
        return "NIL"
    for tok in re.findall(r"\.?\d[\d,]*(?:\.\d+)?", evidence or ""):
        try:
            if abs(float(tok.replace(",", "")) - value) < 1e-9:
                return tok
        except ValueError:
            continue
    return str(value)


def check_item(item: dict, block: str) -> str | None:
    """Return an error string if the extracted item is not grounded in the block."""
    if not isinstance(item, dict):
        return "item is not an object"
    if item.get("metric") not in CATALOGUE:
        return f"metric '{item.get('metric')}' not in catalogue"
    ev = " ".join(str(item.get("evidence") or "").split())
    flat = " ".join(block.split())
    if not ev or ev not in flat:
        return f"evidence for {item['metric']} not found verbatim in profile"
    v = item.get("value")
    if v is None and "nil" not in ev.lower():
        return f"null value for {item['metric']} but evidence does not say NIL"
    if v is not None:
        try:
            v = float(str(v).replace(",", ""))
        except ValueError:
            return f"value '{v}' for {item['metric']} is not a number"
        nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", ev)]
        if not any(abs(n - v) < 1e-6 for n in nums):
            return f"value {v} for {item['metric']} does not appear in its evidence"
    return None


class IslandProfileAgent(BaseAgent):
    agent_id = "island_profile_agent"
    uses_llm = True
    description = "Segment island profiles, LLM key-value extraction with groundedness gate, teacher fallback"

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        path = str(ctx.path)
        n_pages = len(page_texts(path))
        islands = {r["alias"]: r["entity_id"] for r in ctx.conn.execute(
            "SELECT a.alias, a.entity_id FROM alias a JOIN location l ON l.location_id=a.entity_id "
            "WHERE a.entity_type='location' AND l.level='island' AND a.lang='en'")}
        period = parse_period(ctx.document.get("period_label") or "", "fiscal_year")
        blocks = []
        for p in range(1, n_pages + 1):
            text = page_text_unicode(path, p)
            for lid, block in segment_islands(text, islands):
                blocks.append((p, lid, block))
        ctx.tracer.decision("segment_islands", "rule", {"blocks": len(blocks), "islands": [b[1] for b in blocks]})
        stats = {"blocks": len(blocks), "llm_items": 0, "llm_rejected": 0, "teacher_filled": 0}
        for page, lid, block in blocks:
            focus = self.tool(ctx, "select_relevant_lines", relevant_lines, block=block,
                              summarize=lambda s: {"chars": len(s), "lines": s.count("\n") + 1})
            items = []
            if ctx.use_llm and ctx.llm.enabled:
                items = self._llm_extract(ctx, lid, focus, stats)
            teacher = teacher_extract(block)
            have = {(i["metric"], i.get("qualifier")) for i in items}
            missing = [t for t in teacher if (t["metric"], t["qualifier"]) not in have]
            if missing:
                stats["teacher_filled"] += len(missing)
                ctx.tracer.decision("teacher_fill", "rule", {"island": lid, "filled": [m["metric"] for m in missing]})
                for t in missing:
                    t["by"] = "rule"
                items += missing
            for it in items:
                metric = it["metric"]
                unit = it.get("unit") if it.get("unit") in ctx.normalizer.names["unit"] else CATALOGUE[metric][0]
                if metric == "area_under_cultivation" and "hect" in it.get("evidence", "").lower():
                    unit = "ha"
                value = it.get("value")
                value = float(str(value).replace(",", "")) if value not in (None, "") else None
                if it.get("by") == "model":
                    it["raw"] = raw_from_evidence(it.get("evidence", ""), value)
                dims = {"qualifier": it["qualifier"]} if it.get("qualifier") else {}
                p = period
                if metric in ("population", "households"):
                    p = parse_period("2011", "calendar_year")
                    dims["source_census"] = "Census 2011"
                result.records.append(make_record(
                    ctx, self.agent_id, metric_id=metric, location_id=lid, period=p, value=value,
                    value_raw=str(it.get("raw") or it.get("value")), missing_reason=None if value is not None else "nil",
                    unit_id=unit, dims=dims, page=page, table_ref=f"profile:{lid}", row_label=it.get("evidence", "")[:120],
                    col_label=metric, confidence=0.9 if it.get("by") != "rule" else 1.0))
        result.stats = stats
        ctx.tracer.output("records", {"n": len(result.records), **stats})
        return result

    def _llm_extract(self, ctx: AgentContext, lid: str, focus: str, stats: dict) -> list[dict]:
        user = build_prompt(focus)
        for attempt in (1, 2):
            r = self.tool(ctx, "llm_extract_profile", lambda: ctx.llm.json_call(SYSTEM, user, max_tokens=2000),
                          summarize=lambda r: {"ok": r.ok, "error": r.error, "items": len(r.parsed) if isinstance(r.parsed, list) else 0,
                                               "latency_s": round(r.latency_s, 1)},
                          island=lid, attempt=attempt)
            if not r.ok or not isinstance(r.parsed, list):
                ctx.tracer.error("llm_extract_profile", r.error or "not a list", handled_by="retry" if attempt == 1 else "teacher_fallback")
                user += "\nReturn ONLY a JSON list."
                continue
            good, errors = [], []
            for it in r.parsed:
                err = check_item(it, focus)
                if err:
                    errors.append(err)
                else:
                    it["by"] = "model"
                    good.append(it)
            stats["llm_items"] += len(good)
            stats["llm_rejected"] += len(errors)
            ctx.tracer.decision("extract_profile", "model", {"island": lid, "accepted": len(good), "rejected": errors[:5]})
            # dedupe by (metric, qualifier): first grounded answer wins
            seen, out = set(), []
            for it in good:
                key = (it["metric"], it.get("qualifier"))
                if key not in seen:
                    seen.add(key)
                    out.append(it)
            return out
        return []
