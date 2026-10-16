# Phase 2 interim report

## Agriculture information system for Andaman and Nicobar Islands

**Run shown:** `9e1171369c9e` — 16 October 2026  
**Sources:** the 17 files supplied in Phase 1

### What we made

We wrote a Python program that reads the Phase 1 agriculture files and saves useful text and numbers in a local SQLite database. For each result, the database keeps the original source and its page or table position when available.

The files have different formats, so the manifest assigns each one to a small reader. A fixed Python rule chooses the reader. There is no LLM supervisor.

### Readers and sources

- **PDF table reader:** crop statistics, monthly food prices, area and production reports, and the A&N land-cover data table. It saves original table cells and converts selected rows into searchable values.
- **PDF text reader:** island profiles, food-processing report and subsidy report. It saves source text and selected lines that contain numbers and agriculture terms.
- **Image OCR reader:** reads the Phase 1 agriculture census screenshot with Tesseract. It recognizes eight values from the Total row: holdings and operated area by type.
- **Map legend reader:** reads titles, labels, legend items and source notes on the two Phase 1 map files. It does not create digital map boundaries.
- **Chart reader:** reads the Andaman & Nicobar group on Chart 34 in the LULC atlas. It measures colored bar heights against the chart axis and saves five approximate values.
- **Hindi label decoder:** converts selected Kruti Dev font labels to Hindi with a fixed character mapping. It does not translate sentences.

All 17 sources now have a reader. Sixteen completed their stated job; one atlas chart is partial because the bars have no exact printed labels. A loaded map means its words and legend were captured, not that it is ready for GIS queries.

### What the latest run did

| Result | Count |
|---|---:|
| Sources attempted | 17 |
| Loaded | 16 |
| Partial | 1 |
| Pending, skipped or failed | 0 |
| Saved table cells | 45,139 |
| Structured observations | 21,158 |
| Values checked against source cells/text/OCR | 21,153/21,153 |
| Approximate chart readings, reported separately | 5 |
| Basic Statistics example values | 4/4 correct |
| Hindi label examples | 5/5 correct |
| Local routes / tool sequences / tool inputs | 17/17 each |
| Unit tests | 5 passed |
| SQLite integrity | `ok` |

Sixteen of seventeen inputs (94.1%) were loaded without manual intervention during the run. This measures whether the assigned reader completed its job; it does not say all 17 documents are fully converted into clean tables. Source selection, downloads and preparation of checked reference values happen outside the run.

### How the readers work together

The workflow is a simple sequential pipeline. It reads the manifest, applies a fixed Python rule to choose one reader for each source, runs that reader, then saves its result, status and trace. The pipeline stops on a recorded status; it does not retry automatically. This keeps routing easy to explain for a small, known set of government documents. A supervisor LLM would add cost and uncertainty without helping choose among these pre-labelled formats.

The local checks are reported separately from the hosted trajectory score. By reader, expected tool inputs and trajectories matched for image OCR (1/1), chart (1/1), map OCR (2/2), PDF tables (9/9) and PDF text (4/4). The source-group status breakdown is in `evaluation/latest_evaluation.json`. These are routing and trace checks, not hand checks of every value.

We used the evaluator types that fit this pipeline: route/tool selection, tool input, expected tool sequence, task status, source-groundedness, and direct checks of selected values. Four numeric examples and five Hindi-label examples have checked references. AgentEvals performed a strict trajectory check and LangSmith recorded 17 examples; its average strict match was 1.00. This score means the tool sequence matched, not that extraction is 100% accurate. We skipped LLM answer quality, safety and relevance judges because the system does not generate conversational LLM answers. Latency and token scores do not help assess this deterministic workflow.

### One example from start to finish

The manifest recognizes `agri census 2015-16.png` as an English image. The router selects `image_ocr_agent`. Tesseract reads the screenshot and eight small cells in its Total row. Python saves the values with the image name, source page, cell position, OCR reader and run ID. The OCR output and tool call are also kept in the text evidence and run trace.

Another example is the atlas chart. The chart reader opens PDF page 102 (printed page 81), locates the Andaman & Nicobar bars and compares their heights with the chart's area axis. The saved approximate readings are about 5.0 lakh ha for evergreen/semi-evergreen woodland, 1.7 lakh ha for degraded woodland, 0.7 lakh ha for littoral/swamp/mangroves, 0.4 lakh ha for deciduous woodland and 0.3 lakh ha for double/triple/annual crop. These are estimates only. The chart prints no exact numbers; for exact LULC values, use the separate A&N data table from 2015-16.

### Challenge and what we tested

The main challenge was that the Phase 1 sources are not all digital tables. Some PDFs contain selectable text, one census is only a screenshot, the maps are pictures, and one atlas chart has bars without printed numbers. We tested pdfplumber on the PDFs and Tesseract 5.5.3 with English OCR on the census image and map pages. The OCR read the census totals and map title/legend; the chart's colored bars could be measured only approximately.

We used simple rules because the sources and desired outputs are known. We kept the original values and locations so a reader can check them. Tesseract is a standard open-source OCR engine; pdfplumber extracts PDF text and table layouts. Neither tool makes a fuzzy chart label into an exact number. The atlas chart stays marked partial for that reason. The A&N-specific 2015-16 land-cover table is used for exact values.

The Hindi labels use a deterministic Kruti Dev mapping. Five examples from the Basic Statistics sources passed. This is not a trained Hindi model. No LLM, adapter or fine-tuning was used, so a base-model versus adapter comparison is not applicable to this implementation unless the instructor explicitly requires one.

### Database and source trail

SQLite keeps source documents, runs, page text, raw table cells, structured observations, evidence lines and tool traces. Each observation records its metric, value, unit, place, period, source page and table coordinates when available. Blank printed values are left missing; they are not turned into zero. A provenance view joins the observation back to its file and source type.

Example: Paddy production is stored as **13,490.2 MT**, from `basic statistics report 2024-25.pdf`, page 1, table 1, row 4, column 6. The record names `pdf_table_agent` and its run.

### Evaluation and LangSmith

Local checks found all 17 source paths and routes, and their tool traces matched the planned readers. Four selected crop values and five Hindi labels matched checked examples. The latest local run has 21,153 source-cell/text/OCR matches; the five visual chart readings are reported separately.

The latest LangSmith dashboard screenshot shows the dataset `agriculture-phase2-9e1171369c9e`: 17/17 runs completed with an average strict trajectory match of 1.00. This checks whether tool calls followed the expected sequence. It is not a score for extraction accuracy. The experiment name is shortened in the screenshot as `phase2-agent-trajectories-485b...`. A copy of the screenshot is included in the logs.

### Remaining limits and next work

- The atlas chart values are estimates and should not be used as exact official statistics.
- The maps have text and legend extraction only; the package does not create GIS boundaries or calculate areas from map pixels.
- Some large source tables are still kept as raw cells instead of fully normalized records.
- The source list was prepared from the Phase 1 materials; automatic source discovery and downloading are not included.
- The hosted trajectory check has been run for the latest code; it should not be described as an extraction-accuracy evaluation.
- The current reader records failures but does not retry them automatically. Source collection and downloading remain manual.

### Source and licence note

The corpus contains government and official publications supplied in Phase 1. The supplied copies do not state a reuse licence for every file. We therefore describe their publishers as government/official and do not claim that a specific government reuse licence (GRL) has been confirmed.

### Plain answer on Phase 2

The code, corpus, manifest, database, local evaluation, logs, report and presentation guide are assembled. Every source has a reader and an honest status. The atlas chart is the one partial source; its numbers are approximate. This is a demonstrable Phase 2 pipeline, not a complete agriculture knowledge base.
