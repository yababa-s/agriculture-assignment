# Phase 2 Interim Report

## Goal

Build a small, inspectable pipeline for the agriculture documents collected in Phase 1 for Andaman & Nicobar Islands. The pipeline routes each document to a reader, extracts evidence from the file, and saves results with a source citation.

## Sources and scope

The package includes the 17 source files present in the uploaded Phase 1 folder. The source manifest computes a checksum for each included file. The uploaded Phase 1 materials do not provide a per-file download URL or verified collection date, so the manifest marks those as unavailable instead of guessing. Original source and licensing notes are retained where provided in Phase 1.

## Implementation

Two readers are implemented: `pdf_table_agent` captures digital PDF tables and normalizes the main crop/year table in the two Basic Statistics PDFs; `pdf_text_agent` stores page text and exact numbered evidence lines from profiles and narrative PDFs. The router uses source groups in the manifest. Screenshot OCR and atlas chart digitisation are pending. Raster maps are explicitly skipped.

## Challenge

The Basic Statistics files contain Hindi labels encoded with the Kruti Dev legacy font. Their text layer contains Latin-looking codes rather than Unicode Hindi. This submission uses a small, tested word-level decoder on source labels and keeps the original printed text as evidence. The paired Basic Statistics PDFs provide development and held-out examples. No LLM is needed for these known labels, and no model training is claimed.

## Database

SQLite stores source documents, extraction runs, page text, table cells, selected normalized observations, exact text evidence and traces. The provenance view links an observation to the source file, source type, page/cell, agent and run. See `docs/schema.md`.

## Evaluation and current limits

The local evaluator checks manifest coverage, expected routing and tool sequences, tool input paths, source-cell groundedness, four values from the 2024–25 Basic Statistics page against hand-checked source values, and five Hindi decoder examples. Its actual result is in `evaluation/latest_evaluation.json`. It is deliberately limited: four numeric values do not validate every row. An optional AgentEvals/LangSmith adapter is included, but the hosted evaluation was not run because the runtime had neither package installed nor a LangSmith API key. No LLM or LoRA run is claimed.

The verified full run (`83db8555923d`) on 16 October 2026 found all 17 manifest files, saved 45,708 table cells, 84 normalized observations and 688 exact text/evidence lines. All 17 routes and local tool trajectories matched the manifest; all 14 tool inputs were valid and all 84 normalized observations matched their source cells. It completed 12 documents, marked two partial, one pending and two as deliberate skips, with no failed documents. Four out of four direct numeric checks and five out of five decoder checks passed; four unit tests passed. Fully handled without human intervention (loaded or deliberate skip) was 14/17. The SQLite integrity check passed with no foreign-key violations.

The Phase 2 map is complete in the sense that each supplied document is assigned to a reader, pending status or explicit skip. Extraction coverage is not complete: OCR, chart digitisation and full normalization of price/area/LULC tables remain future work. A working sample demonstrates the table and text readers; Phase 3 should expand extraction and query support.
