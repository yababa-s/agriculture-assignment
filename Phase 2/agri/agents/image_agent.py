"""G6 image agent: OCR a table screenshot, rebuild the grid, map columns, unroll.

  tool  : macOS Vision OCR (ocrmac) -> text boxes with confidence
  rule  : cluster boxes into rows (y) and columns (x of the numeric cells)
  rule  : header words -> metric (holdings count / area) x holder type; LLM fallback
  rule  : sub-total rows ("Marginal(1+2)") flagged is_total_row; row sums cross-checked
G8 raster maps are not interpreted (brief: no raster interpretation); the router skips them.
"""
from __future__ import annotations

import re
from statistics import median

from agri.agents.base import AgentContext, AgentResult, BaseAgent, make_record
from agri.tools.parsing import parse_period, parse_value

HOLDER = {"indl": "individual", "joint": "joint", "instl": "institutional", "total": "total"}


def ocr_boxes(path: str) -> list[dict]:
    from ocrmac import ocrmac
    from PIL import Image
    img = Image.open(path)
    w, h = img.size
    out = []
    for text, conf, (x, y, bw, bh) in ocrmac.OCR(img, recognition_level="accurate").recognize():
        # Vision returns normalised boxes with origin bottom-left
        out.append({"text": text.strip(), "conf": round(float(conf), 3), "x0": x * w, "x1": (x + bw) * w,
                    "yc": (1 - y - bh / 2) * h, "h": bh * h})
    return out


def _holder(text: str) -> str | None:
    t = text.lower().strip(" .")
    for key, val in (("ind", "individual"), ("joint", "joint"), ("inst", "institutional"), ("total", "total")):
        if t.startswith(key) and len(t) <= 6:
            return val
    return None


def split_box(b: dict) -> list[dict]:
    """OCR sometimes merges neighbouring cells ('120 5154'); split on spaces, sharing the width by length."""
    toks = b["text"].split()
    if len(toks) == 1 or not any(parse_value(t)[0] is not None for t in toks) and not all(_holder(t) for t in toks):
        return [{**b, "xc": (b["x0"] + b["x1"]) / 2}]
    total = sum(len(t) for t in toks) + len(toks) - 1
    out, x = [], b["x0"]
    for t in toks:
        w = (b["x1"] - b["x0"]) * len(t) / total
        out.append({**b, "text": t, "x0": x, "x1": x + w, "xc": x + w / 2})
        x += w + (b["x1"] - b["x0"]) / total
    return out


def rows_from_boxes(boxes: list[dict]) -> list[list[dict]]:
    boxes = sorted(boxes, key=lambda b: b["yc"])
    tol = median([b["h"] for b in boxes]) * 0.6 if boxes else 5
    rows, cur = [], []
    for b in boxes:
        if cur and abs(b["yc"] - cur[-1]["yc"]) > tol:
            rows.append(sorted(cur, key=lambda b: b["x0"]))
            cur = []
        cur.append(b)
    if cur:
        rows.append(sorted(cur, key=lambda b: b["x0"]))
    return rows


class ImageTableAgent(BaseAgent):
    agent_id = "image_table_agent"
    uses_llm = True
    description = "OCR screenshot tables -> grid -> holdings observations"

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        boxes = self.tool(ctx, "ocr_image", ocr_boxes, path=str(ctx.path),
                          summarize=lambda bs: {"boxes": len(bs), "mean_conf": round(sum(b["conf"] for b in bs) / max(1, len(bs)), 3),
                                                "low_conf": [b["text"] for b in bs if b["conf"] < 0.5][:10]})
        rows = [[t for b in r for t in split_box(b)] for r in rows_from_boxes(boxes)]
        text_rows = [[b["text"] for b in r] for r in rows]
        title = next((" ".join(r) for r in text_rows if any("census" in t.lower() for t in r)), "")
        period = parse_period(title or ctx.document.get("period_label") or "", "census_round") \
            or parse_period(ctx.document.get("period_label") or "2015-16", "census_round")
        hdr_i = next((i for i, r in enumerate(rows) if sum(1 for b in r if _holder(b["text"])) >= 6), None)
        header_words = " ".join(t for r in text_rows[max(0, (hdr_i or 0) - 3):(hdr_i or 0) + 1] for t in r).lower()
        layout_ok = hdr_i is not None and "holding" in header_words and "area" in header_words
        if not layout_ok:
            ctx.tracer.error("unexpected_ocr_layout", header_words[:200], handled_by="mark_needs_review")
            result.status = "partial"
            result.notes.append("OCR header did not match the holdings layout")
            return result
        hcols = [(b["xc"], _holder(b["text"])) for b in rows[hdr_i] if _holder(b["text"])][:8]
        col_specs = [("holdings_count" if k < 4 else "holdings_area", "count" if k < 4 else "ha", h) for k, (_, h) in enumerate(hcols)]
        centers = [x for x, _ in hcols]
        half = min(b - a for a, b in zip(centers, centers[1:])) / 2
        ctx.tracer.decision("map_ocr_columns", "rule", {"header_row": text_rows[hdr_i], "period": period["period_label"],
                                                         "columns": [f"{m}:{h}" for m, _, h in col_specs]})
        derived = 0
        for r in rows[hdr_i + 1:]:
            if any("contents are owned" in b["text"].lower() for b in r):
                break
            cells: list[dict | None] = [None] * len(centers)
            label_parts = []
            for b in r:
                v = parse_value(b["text"])[0]
                if v is None or b["xc"] < centers[0] - half:
                    label_parts.append(b["text"])
                    continue
                k = min(range(len(centers)), key=lambda i: abs(centers[i] - b["xc"]))
                cells[k] = b
            label = re.sub(r"^\d+\s+", "", " ".join(label_parts)).strip(" :")
            if not label or all(c is None for c in cells):
                continue
            is_total = bool(re.search(r"\(|total", label, re.I))
            vals = [parse_value(c["text"])[0] if c else None for c in cells]
            notes = [""] * len(cells)
            for base in (0, 4):
                blk = vals[base:base + 4]
                if blk.count(None) == 1 and blk[3] is not None:
                    miss = base + blk.index(None)
                    vals[miss] = round(blk[3] - sum(v for v in blk[:3] if v is not None), 2)
                    notes[miss] = "OCR dropped this cell; derived as row total minus other holder types"
                    derived += 1
                    ctx.tracer.error("ocr_missing_cell", {"row": label, "column": col_specs[miss][2], "derived": vals[miss]},
                                     handled_by="derive_from_row_total")
                elif None not in blk and abs(sum(blk[:3]) - blk[3]) > 0.01 * max(1, blk[3]):
                    ctx.tracer.error("row_sum_mismatch", {"row": label, "values": blk}, handled_by="flag_warning")
            for k, ((metric, unit, holder), cell, v) in enumerate(zip(col_specs, cells, vals)):
                rec = make_record(ctx, self.agent_id, metric_id=metric, location_id="AN", period=period, value=v,
                                  value_raw=cell["text"] if cell else "", missing_reason=None if v is not None else "unparseable",
                                  unit_id=unit, dims={"size_class": label, "holder_type": holder}, page=1, table_ref="ocr_table",
                                  row_label=label, col_label=f"{metric}:{holder}", is_total_row=is_total or holder == "total",
                                  confidence=0.5 if notes[k] else round(cell["conf"], 3) if cell else 0.0)
                if notes[k]:
                    rec["validation"], rec["validation_note"] = "warning", notes[k]
                elif cell and cell["conf"] < 0.5:
                    rec["validation"], rec["validation_note"] = "warning", f"low OCR confidence {cell['conf']}"
                result.records.append(rec)
        result.stats = {"ocr_boxes": len(boxes), "derived_cells": derived}
        ctx.tracer.output("records", {"n": len(result.records), **result.stats})
        return result
