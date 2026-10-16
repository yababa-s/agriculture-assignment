# Simple demo and viva notes

## Before the presentation

1. Open PowerShell in the `Phase2_Submission` folder.
2. Confirm Tesseract is available:

   ```powershell
   & "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
   ```

   The list should include `eng`.

3. Run the project:

   ```powershell
   python phase2/run_pipeline.py --fresh
   python phase2/evaluate.py
   ```

4. If you want to show the automated code checks too:

   ```powershell
   python -m unittest discover -s phase2/tests -v
   ```

`--fresh` rebuilds the local SQLite database from the 17 bundled Phase 1 sources and writes a new trace in `phase2/logs/`. It does not contact the LangSmith service.

## Eight-minute demonstration

### 1. Show the source list (one minute)

Open `phase2/data/manifest.csv`. Point out that each Phase 1 file has an ID, type, language, reader status and checksum. Explain that Python rules choose the reader; no LLM is routing documents.

### 2. Show an English crop table (two minutes)

Run:

```powershell
python phase2/query_db.py zone-table
```

This prints the PDF name, page, table, row and column for saved cells from the 2023-24 crop area and production PDF. Then show a crop value query:

```powershell
python phase2/query_db.py paddy-provenance
```

Expected example: Paddy production of **13,490.2 MT** in the 2024-25 Basic Statistics source. The output includes where it was printed and which reader/run stored it.

### 3. Show the Hindi labels (one minute)

In the same Basic Statistics source, labels are printed with the legacy Kruti Dev font. Show that `python phase2/evaluate.py` reports five checked decoder examples. Explain that a fixed character mapping converts these labels; this is not model training or translation.

### 4. Show the census image OCR (one minute)

Run:

```powershell
python phase2/query_db.py census
```

This shows eight values read from the screenshot's Total row: individual, joint, institutional and total holdings, plus the corresponding operated area. Each record names the image source, OCR reader, run and cell location.

### 5. Show maps and the chart carefully (one minute)

Run:

```powershell
python phase2/query_db.py map-legend
python phase2/query_db.py lulc-chart
```

The first command shows text read from the A&N map and India map: titles, legend or source notes. The second shows approximate bar-height readings for Andaman & Nicobar from atlas PDF page 102 (printed page 81, Chart 34, 2022-23). The chart has no printed bar values. Say clearly that these are estimates; cite the separate 2015-16 LULC data table for exact area values. We did not create map boundaries or calculate areas from pixels.

### 6. Show checks and LangSmith (two minutes)

Open `phase2/evaluation/latest_evaluation.json`. It shows local route, tool-call, source-provenance, four checked numeric values, five Hindi decoder examples and automation status. Explain that the chart remains partial because its numbers are not printed.

The earlier LangSmith experiment checked tool trajectories only. Open the saved experiment/screenshot in `phase2/logs/` if asked. Do not describe its strict-match score as an extraction-accuracy score. If you run the hosted evaluation again, it creates a fresh experiment for the current run; use your own API key through the environment variable and never paste the key into the report or screenshots.

## What happens to one file

**Source → manifest rule → reader/tool → result → database and trace.**

For example, the manifest identifies the census screenshot as an image. The router selects `image_ocr_agent`. Tesseract reads the English text and the eight Total-row cells. Python stores recognized numeric values in `observation`, OCR lines in `page_text`/`text_fact`, and the tool call in the run trace. A failed OCR call is recorded as a failure instead of silently inventing a value.

## Short viva answers

**What is an agent in this project?** A small Python reader with one job, such as extracting PDF tables, PDF text, image text, map legends or chart bars.

**Does an LLM choose which agent to run?** No. A fixed manifest rule chooses the reader because the document groups and formats are known.

**Did you train or fine-tune a model?** No. OCR uses Tesseract's English language data. The Hindi labels use a tested fixed Kruti Dev character decoder.

**How do you know where an answer came from?** The database keeps the source document and type, run, reader, page, and table/row/column where available. Raw text and values are retained as evidence.

**Why is the chart partial?** Bars have no printed numbers. The project estimates selected bar heights from the chart axis and marks them approximate. It uses the Phase 1 LULC data table for exact values.

**Why are the maps not fully digitized?** They are flattened pictures or a national map page. OCR can read labels and legends, but these files do not provide GIS boundaries that this Phase 2 code can query.

**How much is automatic?** The current run summary gives the exact completed/attempted ratio. Source selection and downloading happen before the run. Review the chart estimate and any OCR error before using a number as official.

**What would Phase 3 add?** More source normalization, stronger OCR/chart validation, better automation, and actual GIS data if official boundary files become available.
