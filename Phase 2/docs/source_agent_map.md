# Sources, agents and responsibilities

Every one of the 20 corpus files is mapped to exactly one agent (or to an explicit *skip* decision).
Grouping follows **how a file has to be read**, not its topic: files that share format, language,
access method and extraction difficulty share an agent. The mapping is executable: the `source_group`
column in `data/manifest.csv` is what the router uses for known files (`agri/agents/router.py`).

## 1. Source to agent map

| Doc | File | Publisher | Modality / language | Group | Agent | Status |
|---|---|---|---|---|---|---|
| D01 | 42-Zone-Wise Area and Production of Crops During 2023-24.pdf | Dept. of Agriculture | digital PDF, English | G1 | matrix_table_agent | implemented |
| D02 | 47-Area and Production 2025-26.pdf | Dept. of Agriculture | digital PDF, English | G1 | matrix_table_agent | implemented |
| D03-D06 | Basic Statistics Year 2021-22 … 2024-25 | DES A&N | digital PDF, **Hindi in Kruti Dev legacy font** + English | G2 | bilingual_table_agent | implemented (some tables partial, see limits) |
| D07 | 37-7 Basic Statistics Report 2023-24 Machinery Farmers.pdf | DES A&N | digital PDF, English, **rotated headers**, islands as rows | G1 | matrix_table_agent | implemented (1 column needs LLM) |
| D08-D10 | IslandwiseStatistical 2022-23 … 2024-25 | DES A&N | digital PDF, Hindi (Kruti Dev) headings + English **prose key-values** | G4 | island_profile_agent | implemented |
| D11-D13 | Fooditems 2023, 2024, 2025 | DES A&N | digital PDF, English; **D13 grid is a raster image** | G3 | price_table_agent | implemented |
| D14 | food processing for sustainable growth.pdf | MoFPI (EY) | digital PDF, English narrative | G5 | narrative_agent | implemented (LLM facts) |
| D15 | subsidies 2024-25.pdf | Dept. of Agriculture | digital PDF, English budget memoranda | G5 | narrative_agent | implemented |
| D16 | agri census 2015-16.png | DES A&N (web page) | **screenshot**, English | G6 | image_table_agent | implemented |
| D17 | Andaman Nicobar LULC 2015-16 data.pdf | Bhuvan / NRSC | digital PDF table, English | G7 | lulc_agent | implemented |
| D18 | India LULC atlas 2024.pdf | NRSC | 118-page atlas, charts without printed values | G7 | lulc_agent | **pending**: needs chart digitisation |
| D19 | Map of India LULC 2024-25.pdf | NRSC | single raster map | G8 | skip (router) | out of scope by brief (no raster interpretation) |
| D20 | Andaman Nicobar LULC 2015-16 map.jpg | Bhuvan | 9919×7019 raster map | G8 | skip (router) | out of scope by brief; the same statistics come from D17 |

Unseen files (instructor documents) are not in the manifest. The router fingerprints them and asks the
LLM to choose an agent; if the reply is not a registered agent, a fingerprint heuristic decides.

### Why this grouping fits the sources

* **G1 vs G2** look alike (ruled statistical tables) but G2 hides Hindi behind the Kruti Dev font,
  where the text layer is ASCII gibberish (`Qlyksa dk uke` = फसलों का नाम). Mixing them would either
  corrupt English labels (decoding English as Hindi) or leave Hindi labels unreadable, so only G2 runs the decoder.
* **G3** is tabular but has one fixed layout repeated 72 times (12 months × 2 series × 3 years),
  with rotated headers and, in 2025, ruling lines that exist only as a background image. A specialist
  agent anchored on the title and the printed column-number row is cheaper and more reliable than
  generic header reading, and it can cross-check every price against the printed % variation columns.
* **G4** is not a table at all: two columns of prose interleaved in the text layer. This is where the
  LLM does the core extraction, so it gets its own agent, groundedness gate and fine-tuning data.
* **G5** narrative files need segmentation (scheme by scheme) plus fact extraction with evidence spans.
* **G6** is an image, so it needs OCR and geometric reconstruction of the grid before anything else.
* **G7** LULC tables use NRSC class hierarchies (L1/L2) and cover all UTs; the agent keeps only A&N columns.
* **G8** raster maps: the brief says to treat maps as vector/tabular data where available and not to
  interpret rasters, so the router records an explicit *skip* decision instead of leaving them unmapped.

## 2. Agent cards

Decisions are labelled **model** (made by the LLM) or **rule** (fixed code) everywhere: in this
document, in traces (`by=model|rule`) and in the demo.

### router_agent (supervisor)
* **Sources:** all files.
* **Responsibility:** choose the extraction agent, or skip.
* **Input:** a document row (manifest) or a raw path (unseen file).
* **Output:** `agent_id`, decided_by, and a reason.
* **Tools:** `fingerprint_document` (extension, pages, text volume, ruled-table count, language/legacy-font detection, keywords, first-page text) and `llm_route`.
* **Model/rule:** rule for manifest files, model for unseen files; a heuristic fallback catches invalid model replies.
* **Why:** a router is enough because format decides the extraction method; documents do not need multi-agent negotiation.
* **Limits:** the 3B model sometimes confuses G1 and G2 when the legacy font is not obvious on page 1; routing accuracy is reported in the evaluation.

### matrix_table_agent (G1)
* **Input:** digital PDF with ruled tables.
* **Output:** `observation` rows (crop × location × metric × period, plus provenance down to page/table/row/column).
* **Tools:** `pdf_extract_tables` (pdfplumber grid; PyMuPDF re-read of rotated header cells; raster ruling-line detection when no vector lines exist), alias tables, `llm_map_columns`, `llm_resolve_entity`.
* **Decisions:**
  * Rule: header parts are resolved against the gazetteer, metric and period parsers.
  * Model: maps only the columns that rules cannot resolve; its answer is checked against the reference tables and retried once with the errors.
  * Rule: row labels are matched to commodities, locations or metrics; section and total rows are detected.
* **Why pdfplumber + PyMuPDF:** exact cell geometry and the text layer are available, so no OCR error is introduced. PyMuPDF follows text rotation, which pdfplumber does not.
* **Status:** D01 and D02 are fully mapped by rules. In D07, 36/38 columns map by rule and one rotated header ("lle W" = "Well") is left for the model.

### bilingual_table_agent (G2)
* **Input:** DES Basic Statistics PDFs. Output: observations, plus Hindi commodity names added to `alias`/`commodity.name_hi`.
* **Tools:** the G1 tools plus `krutidev_to_unicode` and `split_bilingual_label`: a glyph map with reordering rules for the short-i matra and the reph, and a dictionary test that separates the English half of a label.
* **Rule details:** columns without a location default to the whole UT; section rows ("A. Seedlings", "D. Fertilizers") set the metric; year rows set the period for blocks of rows.
* **Limits:**
  * 13 different table layouts per year. Tables whose header is blank or unreadable are left for the model; without the LLM they are skipped, not guessed.
  * The land-utilisation and cost-of-cultivation tables use item rows (`dims.item`).

### price_table_agent (G3)
* **Input:** monthly price PDFs. Output: `retail_price` observations by commodity, month and variety.
* **Decisions:**
  * Rule: the layout is anchored on the title (month and years) and the printed column-number row.
  * Rule: the printed year row is used as a consistency check, and misprints are flagged as warnings.
  * Model: maps columns only when the layout does not match.
* **Direct check:** every current-month price is re-verified against the printed % variation over each comparison month (about 18,000 checks, 0 mismatches).
* **Limits:**
  * The market/centre is not printed in the files; it is stored as the "A&N retail price survey (DES)" market.
  * Percentage columns are used for checks but not stored.

### island_profile_agent (G4)
* **Input:** island-wise outline PDFs. Output: island-level observations (farmers, depots, fertilizer by nutrient, livestock, fish landed, cultivated area, …).
* **Decisions:**
  * Rule: island segmentation from the gazetteer.
  * Rule: relevant-line selection (cuts the prompt by about 70%).
  * Model: key-value extraction into a 20-metric catalogue, with a verbatim evidence span for each value.
  * Rule: a groundedness gate. The evidence must occur in the text and contain the value, and the metric must be in the catalogue.
  * Rule: the teacher extractor fills items that the model missed or that the gate rejected.
* **Model:** Qwen2.5-3B-Instruct (4-bit) with and without the project LoRA adapter (see evaluation).
* **Limits:**
  * Facts split across the two text columns (e.g. "Manure … Selling Unit-1") are not recovered.
  * One island profile in 2024-25 had its header on two lines (fixed).

### narrative_agent (G5)
* **Input:** budget memoranda and reports. Output: scheme outlay/expenditure observations (rule), plus typed `text_fact` rows with evidence (model).
* **Gate:** the evidence must be found in the page (exact, or fuzzy partial ratio ≥ 92). Facts that fail are rejected and counted.
* **Limits:** the line-item subsidy tables inside memoranda are not yet turned into observations (pending for Phase 3).

### image_table_agent (G6)
* **Input:** screenshot PNG. Output: holdings count and area by size class × holder type.
* **Tools:** `ocr_image` (macOS Vision via ocrmac: local, no data leaves the machine), row clustering, box splitting, and column assignment by x-position under the header.
* **Error handling:**
  * A single cell dropped by OCR is derived from the printed row total and flagged as a warning (confidence 0.5).
  * Larger gaps stay missing.
* **Limits:** only the holdings layout is supported. Other screenshots return `partial` with a note.

### lulc_agent (G7)
* **Input:** LULC tables. Output: `lulc_area` with `dims.lulc_l1/l2` for the Andaman and Nicobar columns only.
* **Pending:** D18 atlas charts carry no printed numbers, so chart digitisation is needed (Phase 3).

### normalizer_agent and validator_agent (shared)
* **Normalizer** (`agri/agents/normalizer.py`):
  * Resolution order: exact alias → cleaned alias → English-only alias → fuzzy (rapidfuzz ≥ 90) → LLM choice among the top-10 candidates.
  * LLM answers are verified and cached back into `alias`.
  * A level hint resolves ambiguous names. For example, "South Andaman" is an agri zone in D01/D02, a district in DES tables, and "South Andaman Island" in island profiles.
* **Validator** (`agri/agents/validator.py`):
  * Errors (record goes to `rejected_record`): unknown ids, invalid periods, a missing value without a reason, negative values, values outside plausible ranges.
  * Warnings (record loaded with a note): non-integer counts, yield ≠ production/area, child locations not summing to their parent.
