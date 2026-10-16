"""Table extraction agents for source groups G1 (English matrices), G2 (bilingual Kruti Dev) and G7 (LULC)."""
from __future__ import annotations

import re

from agri.agents.base import AgentContext, AgentResult, BaseAgent
from agri.agents.table_mapping import coconut_units, detect_unit, llm_map, rule_map, unroll
from agri.tools.parsing import parse_period
from agri.tools.pdf_tools import Grid, extract_grids, page_texts

ROW_METRIC_WORDS = re.compile(r"farmers|depot|tractor|pump|tiller|well|pond|check dam|godown|kisan|organic|vermi|manure", re.I)


def _grid_summary(grids: list[Grid]):
    return [{"ref": g.ref, "rows": len(g.body_rows), "cols": len(g.col_headers),
             "title": g.title[:80], "continued_from": g.continued_from} for g in grids]


class TableAgentBase(BaseAgent):
    uses_llm = True
    loc_hint = "zone"
    period_kind = "agri_year"

    def table_defaults(self, ctx: AgentContext, grid: Grid) -> dict:
        title = grid.title
        period = None
        m = re.search(r"(19|20)\d{2}\s*[-–]\s*\d{2,4}", title)
        period = parse_period(m.group(0), self.period_kind) if m else parse_period(ctx.document.get("period_label") or "", self.period_kind)
        return {"period": period, "period_kind": self.period_kind, "unit_id": detect_unit(title),
                "location_id": None, "metric_id": None}

    def row_entity(self, grid: Grid, spec, ctx: AgentContext | None = None) -> str:
        labels = [r[spec.label_col] for r in grid.body_rows if spec.label_col < len(r)]
        if ctx is not None:
            locs = sum(1 for x in labels if x and ctx.normalizer.resolve("location", x, hint="island", use_llm=False).entity_id)
            if locs >= 0.5 * max(1, len([x for x in labels if x])):
                return "location"
        hits = sum(1 for x in labels if ROW_METRIC_WORDS.search(x or ""))
        return "metric" if hits >= max(2, len(labels) // 3) else "commodity"

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        grids = self.tool(ctx, "pdf_extract_tables", extract_grids, summarize=_grid_summary, path=str(ctx.path))
        if not grids:
            ctx.tracer.error("no_tables", "pdfplumber found no ruled tables", handled_by="mark_needs_review")
            result.status = "failed"
            result.notes.append("no tables found")
            return result
        mapped_by = {"rule": 0, "model": 0, "unmapped": 0}
        for grid in grids:
            defaults = self.table_defaults(ctx, grid)
            spec = rule_map(grid, ctx, defaults, self.loc_hint)
            ctx.tracer.decision("rule_map_columns", "rule", {
                "table": grid.ref, "resolved": len(spec.cols) - len(spec.unresolved), "unresolved": [c.col for c in spec.unresolved],
                "sample": {c.col: [c.location_id, c.metric_id, c.period and c.period["period_label"]] for c in spec.cols[:4]}})
            entity = self.row_entity(grid, spec, ctx)
            ctx.tracer.decision("row_entity", "rule", {"table": grid.ref, "rows_are": entity})
            if entity == "location":
                for c in spec.cols:
                    if c.metric_id and c.period and not c.location_id:
                        c.location_id = "__row__"
            if entity == "metric":
                # metric comes from each row label, so a column only needs location + period
                for c in spec.cols:
                    if c.location_id and c.period and not c.metric_id:
                        c.metric_id = "__row__"
            if spec.unresolved:
                errs = llm_map(grid, spec, ctx, self, self.loc_hint)
                if errs:
                    result.notes.append(f"{grid.ref}: {len(spec.unresolved)} columns unmapped ({errs[0][:80]})")
            for c in spec.cols:
                mapped_by["unmapped" if not c.complete() else c.by] += 1
            recs = unroll(grid, spec, ctx, self.agent_id, result, row_entity=entity, unit_overrides=coconut_units,
                          dims_fn=self.dims_for_row)
            result.records.extend(recs)
        result.stats = {"tables": len(grids), "columns_mapped_by": mapped_by, "unresolved_rows": len(result.unresolved)}
        if mapped_by["unmapped"] or result.unresolved:
            result.status = "partial"
        ctx.tracer.output("records", {"n": len(result.records), **result.stats})
        return result

    def dims_for_row(self, label: str, category: str | None) -> dict:
        return {}


class MatrixTableAgent(TableAgentBase):
    """G1: English crop x zone matrices (area/production) and island-wise machinery tables."""
    agent_id = "matrix_table_agent"
    description = "pdfplumber grid -> rule header mapping -> LLM fallback -> cell unrolling"
    loc_hint = "zone"

    def table_defaults(self, ctx, grid):
        d = super().table_defaults(ctx, grid)
        if "machinery" in ctx.document["file_name"].lower() or "island" in grid.title.lower():
            self.loc_hint = "island"
        return d


class BilingualTableAgent(TableAgentBase):
    """G2: DES Basic Statistics; Hindi in Kruti Dev legacy font next to English."""
    agent_id = "bilingual_table_agent"
    description = "Kruti Dev decode -> table mapping (district columns, year columns) -> unrolling"
    loc_hint = "district"

    def table_defaults(self, ctx, grid):
        d = super().table_defaults(ctx, grid)
        # Basic Statistics tables without a location column describe the whole UT.
        d["location_id"] = "AN"
        d["item_rows_ok"] = True
        title = grid.title.lower()
        if "fertili" in title or any("fertilizer" in (r[0] or "").lower() for r in grid.body_rows[:3]):
            d["metric_id"] = "fertilizer_consumption"
            d["unit_id"] = "mt"
        elif "land utili" in title or any("geographical area" in (r[0] or "").lower() for r in grid.body_rows[:2]):
            d["metric_id"] = "land_use_area"
            d["unit_id"] = "ha"
        elif "cost of cultivation" in title:
            d["metric_id"] = "cost_of_cultivation"
            d["unit_id"] = "inr_lakh"
        elif "seedling" in " ".join((r[0] or "") for r in grid.body_rows[:2]).lower():
            d["metric_id"] = "seedling_distributed"
            d["unit_id"] = "count"
        return d


class LULCAgent(TableAgentBase):
    """G7: NRSC/Bhuvan LULC statistics. Keeps only A&N columns; other UTs are out of scope."""
    agent_id = "lulc_agent"
    description = "LULC class rows x district columns -> lulc_area observations (A&N only)"
    loc_hint = "district"
    period_kind = "census_round"

    def run(self, ctx: AgentContext) -> AgentResult:
        texts = page_texts(str(ctx.path))
        if len(texts) > 20:
            # National atlas: charts without printed values; only text mentions of A&N.
            ctx.tracer.decision("atlas_scope", "rule", {"pages": len(texts), "reason": "values only drawn as bars; no tables"})
            res = AgentResult(status="partial", notes=["Atlas charts carry no printed values: pending chart digitisation"])
            ctx.tracer.output("records", {"n": 0, "pending": "chart digitisation"})
            return res
        result = AgentResult()
        grids = self.tool(ctx, "pdf_extract_tables", extract_grids, summarize=_grid_summary, path=str(ctx.path))
        l1 = None
        for grid in grids:
            hdr = grid.col_headers
            loc_cols = {}
            for i, h in enumerate(hdr):
                res = ctx.normalizer.resolve("location", h, hint="district", use_llm=False)
                if res.entity_id in ("AN_ANDAMAN", "AN_NIC"):
                    loc_cols[i] = res.entity_id
            ctx.tracer.decision("select_columns", "rule", {"table": grid.ref, "kept": loc_cols,
                                                            "dropped": [h for i, h in enumerate(hdr) if i not in loc_cols and i > 1]})
            period = parse_period(ctx.document.get("period_label") or "2015-16", "census_round")
            from agri.agents.base import make_record
            from agri.tools.parsing import parse_value
            for r in grid.body_rows:
                if r[0]:
                    l1 = r[0]
                l2 = r[1] if len(r) > 1 else ""
                if not l2:
                    continue
                for i, loc in loc_cols.items():
                    raw = r[i] if i < len(r) else ""
                    value, missing = parse_value(raw)
                    if missing == "blank":
                        continue  # blank LULC cells mean the class is absent; not stored as facts
                    result.records.append(make_record(
                        ctx, self.agent_id, metric_id="lulc_area", location_id=loc, period=period, value=value,
                        value_raw=raw, missing_reason=missing, unit_id="sq_km",
                        dims={"lulc_l1": " ".join((l1 or "").split()), "lulc_l2": " ".join(l2.split())},
                        page=grid.page, table_ref=grid.ref, row_label=l2, col_label=hdr[i]))
        ctx.tracer.output("records", {"n": len(result.records)})
        return result
