# Challenge: Hindi labels stored in a legacy font

## What the source does

The two Basic Statistics PDFs have an English label alongside Hindi text stored in the old Kruti Dev font. The PDF text layer contains Latin-looking character codes such as `Ukkfj;y` next to `Coconut`. Those characters are not ordinary Hindi Unicode text. A reader that simply copies the PDF text will not get a searchable Hindi label.

## Approaches that exist

- **PDF table extraction:** pdfplumber reconstructs table cells using page lines and word alignment, then returns table → row → cell. That matches the digital text PDFs in this corpus; the project uses it and preserves the cells with their page/row/column positions. See the [pdfplumber table documentation](https://github.com/jsvine/pdfplumber/blob/stable/README.md#extracting-tables).
- **OCR:** Tesseract is an open-source OCR engine with language models for many scripts, including Indic scripts. OCR is useful when the page is an image. It is a different route from this dataset’s digital Hindi text layer. Its Hindi output on the screenshot was not tested in this run. See the [Tesseract manual](https://tesseract-ocr.github.io/tessdoc/).
- **Document-conversion models:** Docling combines layout analysis and table-structure models to convert PDFs. It is a reasonable option for pages whose layout is not represented by clean text/table geometry. It was not installed or tested in this Windows run, so no comparative result is claimed. See the [Docling Technical Report](https://arxiv.org/abs/2408.09869).

## Choice and measured result

The Basic Statistics pages already contain a usable text layer and paired English labels. The project therefore applies a small, explicit Kruti Dev word map to known labels and retains the original encoded string. This avoids an LLM call and avoids OCR for text that is already present in the PDF.

The development examples come from the uploaded 2023–24 Basic Statistics PDF. The 2024–25 PDF supplies two held-out decoder examples and four hand-checked numeric values. The result was 5/5 decoder checks and 4/4 numeric checks. These are small checks, not a claim that all Hindi words or all extracted rows are correct.

## Limits, stated precisely

- This implementation’s decoder supports only the explicit labels in its map. Unknown Kruti Dev strings are preserved, not guessed.
- This project has not established that OCR or document-layout research cannot handle the source. Those alternatives were not tested on the paired Basic Statistics pages.
- The 2025 prices PDF and the LULC atlas remain partial in the local run. Those are current implementation limits, not evidence that existing research has no solution.
- No LLM training or fine-tuning was needed for this deterministic decoder, and none is claimed. If the course requires a base-versus-adapter comparison regardless of the selected approach, that separate requirement remains open.

## Reproduction

```powershell
python phase2/build_decoder_data.py
python -m unittest discover -s phase2/tests -v
python phase2/evaluate.py
```

The script checks that each example’s encoded phrase occurs in the stated uploaded PDF. The evaluation output includes every expected/observed string and source value.
