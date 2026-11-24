"""G3 price agent: DES 'Comparative Statement of Prices' tables (one per month, two series per year).

Rules handle the known layout (label / variety / unit / price columns / %-variation
columns). Every price column needs a resolvable month+year; if a table breaks that
expectation the LLM is asked to map its columns (same llm_map tool as other tables).
The printed %-variation columns are not stored; they are used to re-verify each
extracted current-month price against the comparison prices (direct value check).
"""
from __future__ import annotations

import calendar
import re

from agri.agents.base import AgentContext, AgentResult, BaseAgent, make_record
from agri.agents.table_mapping import ColSpec, TableSpec, llm_map
from agri.tools.parsing import MONTHS, parse_period, parse_value
from agri.tools.pdf_tools import Grid, extract_grids, page_texts

# spaces optional: OCR'd text layers sometimes lose the gaps between words
_TITLE = re.compile(r"Prices\s*of\s*(?P<series>.+?)\s*items?\s*for\s*the\s*month\s*of\s*,?\s*(?P<month>[A-Za-z]+?)(?=[\s,]|\d|$)", re.I)
_UNIT_MAP = [
    (re.compile(r"100\s*gm", re.I), "inr_per_100g"), (re.compile(r"\bkg", re.I), "inr_per_kg"),
    (re.compile(r"doz", re.I), "inr_per_dozen"), (re.compile(r"lit|ltr", re.I), "inr_per_litre"),
    (re.compile(r"pkt|pack|gm|gram", re.I), "inr_per_pack"), (re.compile(r"each|no\.?|nos|piece|pc", re.I), "inr_per_unit"),
]


def price_unit(raw: str) -> str:
    for pat, uid in _UNIT_MAP:
        if pat.search(raw or ""):
            return uid
    return "inr_per_unit"


class PriceTableAgent(BaseAgent):
    agent_id = "price_table_agent"
    uses_llm = True
    description = "Monthly retail price tables -> retail_price observations with %-variation cross-check"

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        grids = self.tool(ctx, "pdf_extract_tables", extract_grids, path=str(ctx.path),
                          summarize=lambda gs: {"tables": len(gs), "refs": [g.ref for g in gs][:30]})
        checks = {"checked": 0, "mismatch": 0}
        for grid in grids:
            recs = self._table(ctx, grid, result, checks)
            result.records.extend(recs)
        result.stats = {"tables": len(grids), "pct_variation_checks": checks}
        ctx.tracer.output("records", {"n": len(result.records), **result.stats})
        return result

    def _title(self, ctx: AgentContext, grid: Grid) -> tuple[str, str | None, list[int]]:
        text = " ".join((page_texts(str(ctx.path))[grid.page - 1] + " " + grid.title).split())
        m = _TITLE.search(text)
        if not m:
            return "", None, []
        tail = text[m.end(): m.end() + 60]
        years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", tail)})
        return m.group("series").strip(), m.group("month"), years

    def _table(self, ctx: AgentContext, grid: Grid, result: AgentResult, checks: dict) -> list[dict]:
        series, month, years = self._title(ctx, grid)
        numrow = next((r for r in grid.body_rows[:4] if [c for c in r if c] == [str(i) for i in range(1, len([c for c in r if c]) + 1)]
                       and len([c for c in r if c]) >= 10), None)
        year_row = next((r for r in grid.body_rows[:4] if sum(1 for c in r if re.fullmatch(r"(19|20)\d{2}", c or "")) >= 3), None)
        ncols = len(numrow) if numrow else len(grid.col_headers)
        page_head = page_texts(str(ctx.path))[grid.page - 1][:600].lower()
        has_variety = "variety" in page_head or any("variety" in h.lower() for h in grid.col_headers)
        prior = [int(c) for c in (year_row or []) if re.fullmatch(r"(19|20)\d{2}", c or "")]
        n_prior = len(years) - 1 if len(years) >= 4 else (len(prior) if 3 <= len(prior) <= 5 else 4)
        header_warning = None
        label_col, variety_col, unit_col = 1, (2 if has_variety else None), (3 if has_variety else 2)
        spec_cols, pct_cols = [], []
        ok_layout = bool(month and years) and ncols == (unit_col + 1) + (2 + n_prior + 1) + (n_prior + 2)
        if ok_layout:
            mi = MONTHS[month.lower()[:3]]
            y = max(years)
            prev = (mi - 1, y) if mi > 1 else (12, y - 1)
            first = unit_col + 1
            layout = [(first, f"{month} {y}"), (first + 1, f"{calendar.month_name[prev[0]]} {prev[1]}")]
            layout += [(first + 2 + k, f"{month} {y - 1 - k}") for k in range(n_prior)]
            layout += [(first + 2 + n_prior, "April 2011")]
            for col, label in layout:
                spec_cols.append(ColSpec(col=col, header=label, location_id="MKT_AN", metric_id="retail_price",
                                         period=parse_period(label), by="rule"))
            pct_cols = list(range(first + 3 + n_prior, ncols))
            # consistency check: the printed year row must agree with the layout
            if year_row:
                printed = [int(c) for c in year_row if re.fullmatch(r"(19|20)\d{2}", c or "")]
                if printed and printed != [y - 1 - k for k in range(n_prior)]:
                    # title + column count agree, so the year row is a misprint: keep the layout, flag records
                    header_warning = f"year row printed {printed}, title says {years}"
                    ctx.tracer.error("year_row_mismatch", {"table": grid.ref, "printed": printed, "expected_from_title": years},
                                     handled_by="trust_title_and_column_count; records flagged warning")
        spec = TableSpec(label_col=label_col, cols=spec_cols, defaults={"period_kind": "calendar_year"})
        ctx.tracer.decision("map_price_columns", "rule", {
            "table": grid.ref, "ruling": grid.ruling, "series": series, "month": month, "years": years, "ncols": ncols,
            "columns": {c.col: c.period and c.period["period_label"] for c in spec_cols}, "pct_cols": pct_cols})
        if not ok_layout:
            ctx.tracer.error("unexpected_layout", {"table": grid.ref, "ncols": ncols, "month": month},
                             handled_by="llm_map_columns")
            spec.cols = [ColSpec(col=i, header=h, location_id="MKT_AN", metric_id="retail_price")
                         for i, h in enumerate(grid.col_headers) if i > unit_col and "variation" not in h.lower()]
            if llm_map(grid, spec, ctx, self, None):
                result.notes.append(f"{grid.ref}: price columns unmapped")
        cols = [c for c in spec.cols if c.complete()]
        records = []
        for r in grid.body_rows:
            if not r or not re.fullmatch(r"\d{1,3}", r[0] or ""):
                continue  # title row, year row, column-number row
            name = " ".join((r[label_col] or "").split())
            variety = " ".join((r[variety_col] or "").split()) if variety_col is not None else ""
            unit_raw = (r[unit_col] or "") if unit_col < len(r) else ""
            if not name or name.isdigit():
                continue
            res = ctx.normalizer.resolve("commodity", name, use_llm=ctx.use_llm, context=f"retail price list, {series}")
            if not res.entity_id:
                result.unresolved.append({"table": grid.ref, "row_label": name})
                continue
            unit = price_unit(unit_raw or variety)
            dims = {"series": "vegetables_fruits" if "veg" in series.lower() else "food_items"} if series else {}
            if variety:
                dims["variety"] = variety
            row_recs = []
            for c in cols:
                raw = r[c.col] if c.col < len(r) else ""
                value, missing = parse_value(raw)
                row_recs.append(make_record(
                    ctx, self.agent_id, metric_id="retail_price", commodity_id=res.entity_id, location_id="MKT_AN",
                    period=c.period, value=value, value_raw=raw, missing_reason=missing, unit_id=unit,
                    unit_raw=unit_raw or None, dims=dims, page=grid.page, table_ref=grid.ref, row_label=name,
                    col_label=c.header, confidence=1.0 if c.by == "rule" else 0.8))
            if header_warning:
                for rec in row_recs:
                    rec["validation"] = "warning"
                    rec["validation_note"] = header_warning + "; "
            self._check_variation(r, cols, pct_cols, row_recs, checks)
            records.extend(row_recs)
        return records

    @staticmethod
    def _check_variation(row, cols, pct_cols, row_recs, checks):
        """Printed '% variation of current over X' must equal (current/X - 1)*100 for each comparison column."""
        if not cols or not pct_cols:
            return
        cur = row_recs[0]
        comps = row_recs[1:1 + len(pct_cols)]
        for rec, pc in zip(comps, pct_cols):
            printed, _ = parse_value(row[pc] if pc < len(row) else "")
            if printed is None or cur["value"] is None or not rec["value"]:
                continue
            checks["checked"] += 1
            expected = (cur["value"] / rec["value"] - 1) * 100
            if abs(expected - printed) > 0.6:
                checks["mismatch"] += 1
                cur["validation"] = "warning"
                cur["validation_note"] = (cur["validation_note"] or "") + \
                    f"pct-variation vs {rec['period_label']}: printed {printed}, recomputed {expected:.2f}; "
