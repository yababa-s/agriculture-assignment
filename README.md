# Phase 2: Andaman & Nicobar agriculture sources

This folder contains a small Python program that reads the 17 files supplied in Phase 1, saves extracted text and values in a local SQLite database, and records where each result came from.

## Run it in Windows PowerShell

Open PowerShell in this folder, then run:

```powershell
python -m pip install -r requirements.txt
python phase2/run_pipeline.py --fresh
python phase2/evaluate.py
python -m unittest discover -s phase2/tests -v
```

The image readers use Tesseract. If PowerShell says `tesseract` is not recognized, the program checks the standard install location `C:\Program Files\Tesseract-OCR\tesseract.exe`. English (`eng`) is required. You can check it with:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

## What the latest local run covers

- Each Phase 1 file has a manifest entry and a reader.
- Digital PDF tables and text are saved with source locations.
- Food-price rows and crop area/production rows are normalized into database observations.
- Tesseract reads the census screenshot and map titles/legends.
- One Andaman & Nicobar chart on atlas PDF page 102 (printed page 81) is read as approximate bar heights. The chart has no printed bar values, so these are clearly marked estimates. Exact land-cover figures come from the separate Phase 1 LULC data table.
- Raster maps are covered for titles, labels and legends only. This code does not create GIS shapes or measure areas from map pixels.

The atlas chart remains **partial**. Every other source can be loaded by its assigned reader. No model training or fine-tuning was done; routing uses Python rules, and the Hindi labels use a small deterministic Kruti Dev decoder.

## Folders

- `corpus/`: copies of the Phase 1 sources used here.
- `phase2/data/manifest.csv`: source list, source type, language, status and file checksums.
- `phase2/db/`: SQLite schema and database.
- `phase2/run_pipeline.py`: routes files, extracts content and writes run logs.
- `phase2/evaluate.py`: checks routes, trace steps, provenance, four reference values and five Hindi decoder examples.
- `phase2/hosted_eval.py`: optional AgentEvals trajectory check recorded in LangSmith. The score evaluates tool paths, not extraction accuracy.
- `phase2/docs/`: plain-language report, source map, schema, demo script and viva notes.
- `phase2/logs/`: run summaries, traces and hosted-evaluation evidence.

See `phase2/docs/demo_and_viva.md` for exactly what to open and say during the demonstration.
