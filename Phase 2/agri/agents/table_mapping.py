"""Generic table understanding shared by the table agents.

Pipeline for one grid:
  rule_map()  - code: split each column header into parts and resolve every part
                against the period parser and the metric/location/unit alias tables.
  llm_map()   - model: for columns the rules could not fully resolve, the LLM proposes
                {location, metric, period, unit}; every proposed id is checked against
                the reference tables and a rejected answer is retried once with the errors.
  unroll()    - code: turn every (row, value-column) cell into an observation record,
                resolving row labels to commodities (or metrics), carrying section headers,
                flagging total rows and decoding Kruti Dev Hindi labels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agri.agents.base import AgentContext, make_record
from agri.db.db import add_alias
from agri.tools.parsing import clean_label, is_numeric_cell, parse_period, parse_value
from agri.tools.pdf_tools import Grid, decode_bilingual

IGNORE_PARTS = {"crops", "crop", "items", "item", "name of crops", "name of crop", "district-wise", "district wise",
                "name of the islands", "particulars", "sl. no.", "sl.no", "name of commodity", "s.no", "name of flowers"}
_UNIT_PAT = [
    (re.compile(r"hect|\bha\b", re.I), "ha"),
    (re.compile(r"\bm\.?t\.?\b|tonne", re.I), "mt"),
    (re.compile(r"sq\.?\s*km", re.I), "sq_km"),
    (re.compile(r"m/\s*nuts|million nuts|milion nuts", re.I), "million_nuts"),
    (re.compile(r"rs\.?\s*in\s*lakh", re.I), "inr_lakh"),
    (re.compile(r"\bnos?\b\.?", re.I), "count"),
]
METRIC_DEFAULT_UNIT = {"area_cultivated": "ha", "production": "mt", "yield": "mt_per_ha"}
TOTAL_RE = re.compile(r"^(total|grand total|sub[- ]?total|g\.?\s*total)\b", re.I)


@dataclass
class ColSpec:
    col: int
    header: str
    location_id: str | None = None
    metric_id: str | None = None
    period: dict | None = None
    unit_id: str | None = None
    dims: dict = field(default_factory=dict)
    by: str = "rule"
    period_from_header: bool = False

    def complete(self) -> bool:
        return bool(self.location_id and self.metric_id and self.period)


@dataclass
class TableSpec:
    label_col: int
    cols: list[ColSpec]
    defaults: dict

    @property
    def unresolved(self) -> list[ColSpec]:
        return [c for c in self.cols if not c.complete()]


def detect_unit(text: str) -> str | None:
    for pat, uid in _UNIT_PAT:
        if pat.search(text or ""):
            return uid
    return None


def _english(part: str, legacy: bool) -> str:
    hi, en = decode_bilingual(part, legacy)
    return en or part


def label_column(grid: Grid) -> int:
    best, best_n = 0, -1
    for c in range(min(3, len(grid.col_headers))):
        n = sum(1 for r in grid.body_rows if c < len(r) and r[c] and not is_numeric_cell(r[c]))
        if n > best_n:
            best, best_n = c, n
    return best


def value_columns(grid: Grid, label_col: int) -> list[int]:
    cols = []
    for c in range(len(grid.col_headers)):
        if c == label_col:
            continue
        cells = [r[c] for r in grid.body_rows if c < len(r) and r[c]]
        numeric = [x for x in cells if is_numeric_cell(x)]
        # serial-number column: 1,2,3... integers only and left of the label
        if c < label_col and all(re.fullmatch(r"\d{1,2}", x) for x in numeric):
            continue
        if numeric and len(numeric) >= 0.5 * len(cells):
            cols.append(c)
    return cols


def rule_map(grid: Grid, ctx: AgentContext, defaults: dict, loc_hint: str | None) -> TableSpec:
    norm = ctx.normalizer
    lc = label_column(grid)
    title_unit = defaults.get("unit_id")
    cols = []
    for c in value_columns(grid, lc):
        header = grid.col_headers[c] if c < len(grid.col_headers) else ""
        spec = ColSpec(col=c, header=header)
        for raw_part in [p for p in header.split(" | ") if p]:
            part = _english(raw_part, ctx.legacy_font)
            low = part.lower().strip()
            if low in IGNORE_PARTS:
                continue
            per = parse_period(part, defaults.get("period_kind", "agri_year"))
            if per and re.fullmatch(r"[\s\w.,&-]*\d{4}[\s\-–/.]*\d{0,4}[\s\w.]*", part) and len(part) <= 25:
                spec.period = per
                spec.period_from_header = True
                rest = re.sub(r"(19|20)\d{2}\s*[-–/.]?\s*\d{0,4}", "", part).strip()
                if not rest:
                    continue
                part = rest
            u = detect_unit(part)
            if u and not spec.unit_id:
                spec.unit_id = u
            m = norm.resolve("metric", part, use_llm=False)
            if m.entity_id and not spec.metric_id:
                spec.metric_id = m.entity_id
                continue
            loc = norm.resolve("location", part, hint=loc_hint, use_llm=False)
            if loc.entity_id and not spec.location_id:
                spec.location_id = loc.entity_id
                continue
            if spec.metric_id and not u:
                # words printed under the metric ("Transferred to PRI", "In Department") qualify it
                spec.dims["channel"] = (spec.dims.get("channel", "") + " " + part).strip()
        if not header.strip():
            # a blank header means the layout was not understood; defaults would silently
            # make every column identical, so leave it unresolved for the model (or skip it)
            cols.append(spec)
            continue
        spec.location_id = spec.location_id or defaults.get("location_id")
        spec.metric_id = spec.metric_id or defaults.get("metric_id")
        spec.period = spec.period or defaults.get("period")
        spec.unit_id = spec.unit_id or METRIC_DEFAULT_UNIT.get(spec.metric_id or "") or title_unit
        cols.append(spec)
    return TableSpec(label_col=lc, cols=cols, defaults=defaults)


MAP_SYSTEM = (
    "You interpret column headers of statistical tables from the Andaman & Nicobar Islands. "
    "For each column you are given, decide which location, metric and period its numbers refer to. "
    "Use ONLY ids from the allowed lists. Reply with a JSON list only, one object per column: "
    "{\"col\": <int>, \"location\": <location id or null>, \"metric\": <metric id or null>, "
    "\"period\": <period as printed, e.g. \"2023-24\" or \"January 2024\", or null>, \"unit\": <unit id or null>}"
)


def build_map_prompt(grid: Grid, targets: list[ColSpec], document: dict, names: dict, legacy: bool,
                     loc_hint: str | None) -> tuple[str, str]:
    """Prompt for the column-mapping task (shared by the agent, the training-set builder and the evaluator)."""
    allowed_loc = ", ".join(k for k in names["location"] if not k.startswith("ISL_") or loc_hint == "island")
    allowed_met = ", ".join(sorted(names["metric"]))
    allowed_unit = ", ".join(sorted(names["unit"]))
    header_lines = "\n".join(f"col {c.col}: \"{_english(c.header, legacy)}\"" for c in targets)
    sample = "\n".join(" | ".join(r[:12]) for r in grid.body_rows[:3])
    user = (f"Document: {document.get('file_name')} (period {document.get('period_label')})\n"
            f"Table title: {grid.title[:200]}\nColumns to map:\n{header_lines}\nFirst rows:\n{sample}\n\n"
            f"Allowed location ids: {allowed_loc}\nAllowed metric ids: {allowed_met}\nAllowed unit ids: {allowed_unit}\n")
    return MAP_SYSTEM, user


def llm_map(grid: Grid, spec: TableSpec, ctx: AgentContext, agent, loc_hint: str | None,
            cols: list[ColSpec] | None = None) -> list[str]:
    """Ask the model to fill unresolved columns. Returns a list of error strings (empty = success)."""
    targets = cols if cols is not None else spec.unresolved
    if not targets or not (ctx.use_llm and ctx.llm.enabled):
        return ["llm_unavailable"] if targets else []
    system, user = build_map_prompt(grid, targets, ctx.document, ctx.normalizer.names, ctx.legacy_font, loc_hint)
    if ctx.feedback:
        user += f"\nYour previous answer was rejected: {ctx.feedback}\n"
    errors: list[str] = []
    for attempt in (1, 2):
        res = agent.tool(ctx, "llm_map_columns", lambda: ctx.llm.json_call(system, user, max_tokens=60 * len(targets) + 80),
                         summarize=lambda r: {"ok": r.ok, "error": r.error, "reply": r.text[:500], "latency_s": round(r.latency_s, 1)},
                         table=grid.ref, columns=[c.col for c in targets], attempt=attempt)
        errors = []
        if not res.ok or not isinstance(res.parsed, list):
            errors.append(res.error or "reply is not a JSON list")
        else:
            by_col = {c.col: c for c in targets}
            for item in res.parsed:
                if not isinstance(item, dict) or item.get("col") not in by_col:
                    errors.append(f"unknown col in {item}")
                    continue
                c = by_col[item["col"]]
                loc, met, unit = item.get("location"), item.get("metric"), item.get("unit")
                if loc and loc not in ctx.normalizer.names["location"]:
                    errors.append(f"col {c.col}: location '{loc}' is not an allowed id")
                    loc = None
                if met and met not in ctx.normalizer.names["metric"]:
                    errors.append(f"col {c.col}: metric '{met}' is not an allowed id")
                    met = None
                if unit and unit not in ctx.normalizer.names["unit"]:
                    unit = None
                per = parse_period(str(item.get("period") or ""), spec.defaults.get("period_kind", "agri_year"))
                c.location_id = loc or c.location_id
                c.metric_id = met or c.metric_id
                c.period = per or c.period
                c.unit_id = unit or c.unit_id or METRIC_DEFAULT_UNIT.get(c.metric_id or "")
                c.by = "model"
        missing = [c.col for c in targets if not c.complete()]
        if missing:
            errors.append(f"columns still incomplete: {missing}")
        if not errors:
            ctx.tracer.decision("map_columns", "model", {c.col: [c.location_id, c.metric_id, c.period and c.period["period_label"]] for c in targets})
            return []
        ctx.tracer.error("llm_map_columns", errors, handled_by="retry_with_feedback" if attempt == 1 else "skip_columns")
        user += f"\nYour previous answer was rejected: {'; '.join(errors)[:600]}\nReturn corrected JSON."
    return errors


def unroll(grid: Grid, spec: TableSpec, ctx: AgentContext, agent_id: str, result, *,
           row_entity: str = "commodity", unit_overrides=None, dims_fn=None) -> list[dict]:
    """Turn a mapped grid into observation records (code only, no model calls except entity fallback)."""
    records = []
    category = None
    row_period = None
    cols = [c for c in spec.cols if c.complete()]
    for r in grid.body_rows:
        raw_label = r[spec.label_col] if spec.label_col < len(r) else ""
        # some tables put the item name in the column after a group label ("A. Seedlings (Nos.)", "Coconut")
        if spec.label_col + 1 < len(r) and r[spec.label_col + 1] and not is_numeric_cell(r[spec.label_col + 1]) \
                and (spec.label_col + 1) not in [c.col for c in spec.cols]:
            if raw_label:
                category = _english(raw_label, ctx.legacy_font)
            raw_label = r[spec.label_col + 1]
        for gc in range(spec.label_col):
            g = r[gc] if gc < len(r) else ""
            if g and not is_numeric_cell(g) and not re.fullmatch(r"\(?[A-Za-z0-9]{1,3}[.)]?", g):
                category = clean_label(_english(g, ctx.legacy_font)) or category
        hi, en = decode_bilingual(raw_label, ctx.legacy_font)
        label = clean_label(en or raw_label)
        has_values = any(c.col < len(r) and r[c.col] and is_numeric_cell(r[c.col]) for c in cols)
        if not has_values:
            # section row; its name may sit in any non-value cell (e.g. column 0 when labels are in column 1)
            name = label or next((clean_label(_english(c, ctx.legacy_font)) for c in r if c and not is_numeric_cell(c)), "")
            per = parse_period(name, spec.defaults.get("period_kind", "agri_year")) if name else None
            if per and re.fullmatch(r"[\d\s\-–/.]+", name):
                row_period = per          # e.g. "2022-23" heading a block of rows
            elif name:
                category = name
            continue
        is_total = bool(TOTAL_RE.match(label))
        commodity_id = metric_override = None
        dims = {}
        location_override = None
        if row_entity == "location":
            lres = ctx.normalizer.resolve("location", label, hint="island", use_llm=False)
            location_override = lres.entity_id
            if not location_override:
                result.unresolved.append({"table": grid.ref, "row_label": label})
                continue
            if "(part)" in label.lower() and category:
                dims = {"listed_under": category}
        elif row_entity == "commodity":
            if is_total:
                if category:
                    cres = ctx.normalizer.resolve("commodity", category, use_llm=False)
                    commodity_id = cres.entity_id
                if not commodity_id:
                    dims = {"row": label, **({"group": category} if category else {})}
            else:
                cres = ctx.normalizer.resolve("commodity", label, use_llm=ctx.use_llm, context=grid.title)
                commodity_id = cres.entity_id
                if not commodity_id:
                    mres = ctx.normalizer.resolve("metric", label, use_llm=False)
                    metric_override = mres.entity_id
                if not commodity_id and not metric_override:
                    if spec.defaults.get("item_rows_ok"):
                        dims = {"item": label, **({"group": category} if category else {})}
                    else:
                        result.unresolved.append({"table": grid.ref, "row_label": label})
                        continue
                if category and not metric_override:
                    # section rows such as "A. Seedlings (Nos.)" / "D. Fertilizers (MT)" carry the metric
                    cat_metric = ctx.normalizer.resolve("metric", category, use_llm=False).entity_id
                    if cat_metric and cat_metric not in ("area_cultivated", "production", "yield"):
                        metric_override = cat_metric
                if commodity_id == "agg_others" and category:
                    dims = {**dims, "group": category}
                if commodity_id and hi:
                    add_alias(ctx.conn, "commodity", commodity_id, hi, origin="kruti_decode")
                    ctx.conn.execute("UPDATE commodity SET name_hi = COALESCE(name_hi, ?) WHERE commodity_id = ?", (hi, commodity_id))
        else:  # rows are metrics/items, e.g. "Farmers/Cultivator", or channels under a metric header row
            mres = ctx.normalizer.resolve("metric", label, use_llm=False)
            metric_override = mres.entity_id
            if not metric_override and category:
                metric_override = ctx.normalizer.resolve("metric", category, use_llm=False).entity_id
                if metric_override:
                    dims = {"channel": label}
            if not metric_override:
                if any(c.metric_id == "__row__" for c in cols):
                    result.unresolved.append({"table": grid.ref, "row_label": label})
                    continue
                dims = {"item": label, **({"group": category} if category else {})}
        if dims_fn:
            dims = {**dims, **dims_fn(label, category)}
        for c in cols:
            if c.col >= len(r):
                continue
            raw = r[c.col]
            value, missing = parse_value(raw)
            if missing == "unparseable" and not raw:
                missing = "blank"
            metric = metric_override or c.metric_id
            unit = c.unit_id
            if metric_override and metric_override != c.metric_id:
                unit = METRIC_DEFAULT_UNIT.get(metric_override) or ctx.normalizer.conn.execute(
                    "SELECT default_unit FROM metric WHERE metric_id=?", (metric_override,)).fetchone()[0]
            if unit_overrides:
                unit = unit_overrides(commodity_id, metric, label, unit)
            records.append(make_record(
                ctx, agent_id, metric_id=metric, commodity_id=commodity_id, location_id=location_override or c.location_id,
                period=row_period if (row_period and not c.period_from_header) else c.period,
                value=value, value_raw=raw, missing_reason=missing, unit_id=unit,
                dims={**c.dims, **dims}, page=grid.page, table_ref=grid.ref, row_label=label,
                col_label=_english(c.header, ctx.legacy_font), is_total_row=is_total or (location_override or c.location_id) == "AN",
                confidence=1.0 if c.by == "rule" else 0.8))
    return records


def coconut_units(commodity_id, metric, label, unit):
    """Coconut production is reported in million nuts in every source (footnotes / '(M/nuts)' labels)."""
    if commodity_id == "coconut" and metric == "production":
        return "million_nuts"
    return unit
