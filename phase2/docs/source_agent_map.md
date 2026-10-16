# Phase 1 files and their readers

All 17 entries below refer to files already supplied in Phase 1. The manifest is the source of truth for their filenames, paths, formats, languages and checksums.

| Sources | Reader | What it reads | Current status |
|---|---|---|---|
| P1-01 to P1-03: Basic Statistics PDFs | `pdf_table_agent` | PDF text and table cells; selected bilingual crop statistics become structured records. | Loaded; only selected tables are normalized. |
| P1-04 to P1-05: island-wise statistics | `pdf_text_agent` | Page text and numbered evidence lines. | Loaded; narrative evidence, not a complete numeric database. |
| P1-06: agriculture census screenshot | `image_ocr_agent` | Tesseract reads screenshot text and eight total-row cells for holdings and operated area. | Loaded; checked values have source page and cell positions. |
| P1-07 to P1-08: food processing and subsidies | `pdf_text_agent` | Page text and exact numbered evidence lines. | Loaded; no subsidy calculation is performed. |
| P1-09 to P1-11: monthly food prices | `pdf_table_agent` | PDF page text; fixed rules convert printed rows into commodity, month, value and unit records. | Loaded; 2025 borderless table is read from text because table-grid detection finds no cells. |
| P1-12: A&N LULC data table | `pdf_table_agent` | Printed land-cover area table. | Loaded; structured values retain location, year, unit and page/table coordinates. |
| P1-13: A&N LULC map image | `map_legend_ocr_agent` | Tesseract reads title, map labels, legend and source notes. | Loaded for text and legend; no GIS polygons or pixel-area calculation. |
| P1-14: India LULC atlas | `lulc_chart_agent` | Renders atlas PDF page 102 (printed page 81), OCRs labels, and estimates colored bar heights for Andaman & Nicobar. | Partial; chart contains no printed values. Estimates are approximate; use P1-12 for exact figures. |
| P1-15: India LULC map PDF | `map_legend_ocr_agent` | Renders page and reads visible title/labels/legend. | Loaded for text and legend; national map is not digitized into GIS geometry. |
| P1-16 to P1-17: area and production PDFs | `pdf_table_agent` | Table cells and normalized crop, location, area, production and yield records. | Loaded. |

## How routing works

Python checks the manifest and uses fixed rules based on a source's ID/group and file format. The program does not ask an LLM to select a reader. Each reader writes tool calls and results to a JSONL trace. A failed reader would get a failed status; the atlas chart remains partial because its bars do not have printed numbers.

## What “loaded” means

Loaded means the assigned reader completed the job described above. It does not mean the entire PDF has been normalized into one clean database table. The map readers capture words and legend labels, not map geometry. The chart reader produces estimates and flags them as estimates. The corpus still has no complete GIS knowledge base.
