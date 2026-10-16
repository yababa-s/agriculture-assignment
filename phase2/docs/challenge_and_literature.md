# Challenge: different sources need different readers

## What the sources look like

The Phase 1 set mixes selectable-text PDFs, a screenshot, scanned map artwork and an atlas chart. The Hindi labels in two Basic Statistics PDFs are also encoded in the older Kruti Dev font: the PDF text may show Latin-looking characters such as `Ukkfj;y` next to `Coconut`. A single extraction method cannot handle all of these formats equally well.

## Approaches that exist

- **PDF table extraction:** pdfplumber reconstructs table cells using page lines and word alignment, then returns table → row → cell. That matches the digital text PDFs in this corpus; the project uses it and preserves the cells with their page/row/column positions. See the [pdfplumber table documentation](https://github.com/jsvine/pdfplumber/blob/stable/README.md#extracting-tables).
- **OCR:** Tesseract is an open-source OCR engine. It was installed and tested with English language data on the census screenshot and map pages. It read the census totals and map labels/legend. Hindi OCR was not used because the census image is English and the Basic Statistics PDFs already have a digital text layer. See the [Tesseract manual](https://tesseract-ocr.github.io/tessdoc/).
- **Document-conversion models:** Docling combines layout analysis and table-structure models to convert PDFs. It is a reasonable option for pages whose layout is not represented by clean text/table geometry. It was not installed or tested in this Windows run, so no comparative result is claimed. See the [Docling Technical Report](https://arxiv.org/abs/2408.09869).

## Choice and measured result

The project selects a reader by format: pdfplumber for PDF text and tables, Tesseract for the screenshot and map images, and a small pixel-height reader for selected atlas bars. For the Hindi table labels, the PDFs already contain paired English labels and a usable text layer, so the code uses an explicit Kruti Dev mapping and keeps the original text. This avoids adding OCR or an LLM to text the PDF already provides.

The development examples come from the uploaded 2023–24 Basic Statistics PDF. The 2024–25 PDF supplies two held-out decoder examples and four hand-checked numeric values. All five decoder checks and four numeric checks passed. The English OCR, map legend OCR and chart pixel reader were run on the supplied screenshot/map/atlas pages. The map OCR found labels, and the chart reader produced five approximate values after scaling colored bars against the printed axis. These results do not prove every OCR result or chart estimate is correct.

## Limits, stated precisely

- This implementation’s decoder supports only the explicit labels in its map. Unknown Kruti Dev strings are preserved, not guessed.
- This project has not established that OCR or document-layout research cannot handle the source. Those alternatives were not tested on the paired Basic Statistics pages.
- The LULC atlas chart remains partial because its bars have no printed values. The pixel reader provides estimates, not official exact numbers. This is a limitation of the chart and current implementation, not evidence that existing research has no solution.
- Map OCR records text only; the flattened images do not provide the GIS boundary features needed for spatial queries.
- No LLM training or fine-tuning was needed for this deterministic decoder, and none is claimed. If the course requires a base-versus-adapter comparison regardless of the selected approach, that separate requirement remains open.

## Reproduction

```powershell
python phase2/build_decoder_data.py
python -m unittest discover -s phase2/tests -v
python phase2/evaluate.py
```

The script checks that each example’s encoded phrase occurs in the stated uploaded PDF. The evaluation output includes every expected/observed string and source value.
