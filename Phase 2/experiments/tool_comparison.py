"""Compare open-source extraction tools on the four hardest cases in our corpus.

Cases (expected values read from the rendered pages):
  C1 raster-ruled grid   D13 p1 : table lines are a background image (no vector rules)
  C2 rotated headers     D07 p1 : column headers printed vertically
  C3 Kruti Dev Hindi     D05 p1 : Hindi set in a legacy font; text layer is ASCII
  C4 screenshot table    D16    : PNG of a web table, needs OCR

Tools: pdfplumber (default settings), PyMuPDF find_tables, Docling (TableFormer; OCR for C4),
and this project's pipeline tools. Run each tool family in an environment that has it:
  .venv/bin/python experiments/tool_comparison.py --tools ours,pdfplumber,pymupdf
  <docling-venv>/bin/python experiments/tool_comparison.py --tools docling
Results -> eval/results/tool_comparison_<tool>.json ; summary table in docs/challenge_literature.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT.parent / "AI Project Data Corpus"
sys.path.insert(0, str(ROOT))

CASES = {
    "C1_raster_grid": {"path": "Market Price Analysis/Fooditems2025.pdf", "page": 1,
                       # commodity -> first two prices on its row (Jan 2025, Dec 2024)
                       "rows": {"Ladies finger": ["136.00", "145.00"], "Onion": ["77.00", "112.50"],
                                "Grape": ["575.00", "575.00"], "Drumstick": ["375.00", "492.00"],
                                "Mutton": ["1000.00", "1000.00"], "Garlic": ["475.00", "475.00"]}},
    "C2_rotated_headers": {"path": "Basic Statistics/37-7. Basic Statistics Report 2023-24- Machinery Farmers.pdf", "page": 1,
                           "headers": ["Transferred to PRI", "In Department", "Loan-cum-", "Private procurement",
                                       "Distribute on subsidy", "RGRP distribute", "Kisan Credit Card", "Pond", "Farmers"]},
    "C3_kruti_dev": {"path": "Basic Statistics/Year 2023-24.pdf", "page": 1,
                     "hindi": ["धान", "नारियल", "सुपारी", "मसाला", "फल", "दलहन", "तिलहन", "सब्जियाँ"]},
    "C4_screenshot": {"path": "Miscellaneous/agri census 2015-16.png", "page": 1,
                      "rows": {"Below 0.5": ["2722", "425", "90", "3237"], "1.0 - 2.0": ["1856", "638", "39", "2533"],
                               "4.0 - 5.0": ["580", "656", "11", "1247"], "Total": ["8412", "3290", "252", "11954"]}},
}


def norm(s) -> str:
    return " ".join(str(s or "").split())


def score_rows(tables: list[list[list[str]]], expected: dict) -> dict:
    """A row is correct if one table row contains the label and the expected numbers in the expected order."""
    hits = {}
    for label, nums in expected.items():
        ok = False
        for t in tables:
            for r in t:
                cells = [norm(c) for c in r]
                text = " ".join(cells)
                if label.lower() not in text.lower():
                    continue
                vals = [v for c in cells for v in c.split() if re.fullmatch(r"[\d.,]+", v)]
                k = len(nums)
                if any(vals[i:i + k] == nums for i in range(len(vals) - k + 1)):
                    ok = True
        hits[label] = ok
    return {"correct": sum(hits.values()), "of": len(hits), "detail": hits}


def score_headers(texts: list[str], expected: list[str]) -> dict:
    blob = " ".join(norm(t) for t in texts).lower()
    hits = {h: h.lower() in blob for h in expected}
    return {"correct": sum(hits.values()), "of": len(hits), "detail": hits}


def score_hindi(texts: list[str], expected: list[str]) -> dict:
    blob = " ".join(texts)
    hits = {w: w in blob for w in expected}
    return {"correct": sum(hits.values()), "of": len(hits), "detail": hits,
            "devanagari_chars": len(re.findall(r"[ऀ-ॿ]", blob))}


# ---------------------------------------------------------------- tools
def run_pdfplumber(path, page):
    import pdfplumber
    if path.suffix.lower() != ".pdf":
        return None
    with pdfplumber.open(path) as pdf:
        p = pdf.pages[page - 1]
        tables = p.extract_tables()
        return {"tables": tables, "texts": [norm(c) for t in tables for r in t for c in r] + [p.extract_text() or ""]}


def run_pymupdf(path, page):
    import pymupdf
    if path.suffix.lower() != ".pdf":
        return None
    with pymupdf.open(path) as d:
        p = d[page - 1]
        tabs = p.find_tables()
        tables = [t.extract() for t in tabs.tables]
        return {"tables": tables, "texts": [norm(c) for t in tables for r in t for c in r] + [p.get_text()]}


def run_docling(path, page):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
    opts = PdfPipelineOptions(do_ocr=path.suffix.lower() != ".pdf", do_table_structure=True)
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts),
                                             InputFormat.IMAGE: ImageFormatOption(pipeline_options=PdfPipelineOptions(do_ocr=True))})
    kw = {"page_range": (page, page)} if path.suffix.lower() == ".pdf" else {}
    res = conv.convert(str(path), **kw)
    tables = []
    for t in res.document.tables:
        df = t.export_to_dataframe()
        tables.append([list(map(str, df.columns))] + df.astype(str).values.tolist())
    md = res.document.export_to_markdown()
    return {"tables": tables, "texts": [md]}


def run_ours(path, page):
    from agri.tools.pdf_tools import extract_grids, page_text_unicode
    if path.suffix.lower() != ".pdf":
        from agri.agents.image_agent import ocr_boxes, rows_from_boxes, split_box
        rows = [[t["text"] for b in r for t in split_box(b)] for r in rows_from_boxes(ocr_boxes(str(path)))]
        return {"tables": [rows], "texts": [" ".join(r) for r in rows]}
    grids = extract_grids(str(path), pages=[page])
    tables = [[g.col_headers] + g.body_rows for g in grids]
    return {"tables": tables, "texts": [h for g in grids for h in g.col_headers] + [page_text_unicode(str(path), page)]}


TOOLS = {"pdfplumber": run_pdfplumber, "pymupdf": run_pymupdf, "docling": run_docling, "ours": run_ours}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", default="ours,pdfplumber,pymupdf")
    a = ap.parse_args()
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    for tool in a.tools.split(","):
        res = {}
        for case, spec in CASES.items():
            path = CORPUS / spec["path"]
            t0 = time.time()
            try:
                r = TOOLS[tool](path, spec["page"])
            except Exception as e:  # noqa: BLE001
                res[case] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
                continue
            if r is None:
                res[case] = {"not_applicable": "tool does not read images"}
                continue
            if "rows" in spec:
                sc = score_rows(r["tables"], spec["rows"])
            elif "headers" in spec:
                # only text the tool assigned to table cells counts (not the raw page text)
                sc = score_headers([c for t in r["tables"] for row in t[:4] for c in row], spec["headers"])
            else:
                sc = score_hindi(r["texts"], spec["hindi"])
            res[case] = {"tables_found": len(r["tables"]), **sc, "seconds": round(time.time() - t0, 1)}
            print(f"{tool:<10} {case:<20} tables={len(r['tables']):<3} score={sc['correct']}/{sc['of']}")
        (out_dir / f"tool_comparison_{tool}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
