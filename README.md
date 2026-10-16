# Phase 2 — Agriculture Information System

This is the simple, reproducible Phase 2 package for the uploaded Andaman & Nicobar Phase 1 corpus.

## What it does

It reads each supplied PDF, assigns it to a format-specific reader, saves page text and detected table cells, and stores selected, clearly identified agricultural values in SQLite with their source page and table. The Hindi examples use the Kruti Dev labels printed in the two Basic Statistics PDFs. A deterministic decoder is used because these Hindi labels are legacy-font text, not scanned handwriting.

## Important status

- This package contains only the corpus supplied in Phase 1: 17 source files (15 PDFs and 2 images). The Phase 1 README is copied as documentation.
- Table and text PDF readers are implemented and tested locally.
- The screenshot OCR reader and chart digitisation are listed as pending. Raster maps are explicitly skipped.
- No language model or LoRA adapter is used. The Hindi component is a deterministic font decoder. The earlier Mac-only MLX/adapter files were not included in this rebuild.
- Local route, tool sequence, tool-input, provenance, and value checks are run. An optional AgentEvals/LangSmith adapter is included, but could not be executed here because those packages and a LangSmith API credential were unavailable; no hosted run is claimed.
- A successful local run produced a database. Two PDFs are partial, one screenshot is pending, and two raster maps are deliberately skipped; see the evaluation report for exact counts.

## Run

Python 3.10 or later is recommended. Install `requirements.txt`, then from this directory run:

```powershell
python phase2/run_pipeline.py --fresh
python phase2/evaluate.py
python -m unittest discover -s phase2/tests -v
```

Optional hosted trajectory evaluation (requires internet access and your own `LANGSMITH_API_KEY`): install `requirements-hosted-eval.txt`, then run `python phase2/hosted_eval.py`. It uploads only source-group labels and tool names, not document text, extracted values, or local file paths.

The pipeline recreates `phase2/db/agriculture_phase2.sqlite`, processes the manifest, and writes local traces under `phase2/logs/`. It does not download sources or models.

## Folder guide

- `corpus/` — the Phase 1 documents, unchanged.
- `phase2/data/manifest.csv` — every supplied source, path, checksum, language, group, and status.
- `phase2/db/schema.sql` — database design.
- `phase2/run_pipeline.py` — routing, extraction and database loading.
- `phase2/evaluate.py` — held-out value checks and per-agent/workflow summary.
- `phase2/hosted_eval.py` — optional AgentEvals trajectory evaluation logged to LangSmith.
- `phase2/docs/` — report, source map, schema, demo and viva notes.
- `phase2/docs/Phase2_Interim_Report.pdf` — printable interim report summarizing results and remaining work.
- `phase2/logs/` — execution traces and evaluation output.
- `phase2/docs/challenge_and_literature.md` — short, evidence-based explanation of the Hindi font challenge and tool choices.

This is a Phase 2 extraction and provenance system. It does not yet answer free-form questions in natural language; that belongs to Phase 3.
