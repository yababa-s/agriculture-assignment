# Which source goes to which reader

All source documents in this submission come from the uploaded Phase 1 folder. The manifest contains 17 data files. A PDF with tables goes to the table reader; a PDF mainly made of prose goes to the text reader. The screenshot OCR reader and chart reader are clearly marked pending. The raster maps are deliberately skipped.

| Phase 1 source group | Files in the supplied corpus | Reader | What it does | Status |
|---|---|---|---|---|
| Area and production | `total area and prod/*` (2 PDFs) | `pdf_table_agent` | Saves PDF pages and table cells with source location. | Implemented; table-cell structure is preserved. |
| Basic Statistics | `basic stats/*` (3 PDFs) | `pdf_table_agent` | Saves table cells; reads the whole-island crop/year table in the two Basic Statistics PDFs into area/production observations. | Implemented for the main crop table; other tables remain raw cells. |
| Island-wise statistics | `island wise stats/*` (2 PDFs) | `pdf_text_agent` | Saves page text and exact numbered evidence lines. | Implemented as source-grounded text capture; no generated claims. |
| Food processing and subsidies | `misc data/food processing…pdf`, `misc data/subsidies…pdf` | `pdf_text_agent` | Saves page text and exact numbered evidence lines. | Implemented; does not calculate subsidy line items. |
| Monthly market prices | `price analysis/*` (3 PDFs) | `pdf_table_agent` | Saves table grids and raw cells. | Implemented; no price normalization yet. |
| LULC statistics | `sat bhuvan data(lulc)/Andaman Nicobar…data.pdf` | `pdf_table_agent` | Saves LULC table cells. | Implemented as table capture. |
| LULC atlas | `India LULC atlas 2024.pdf` | `pdf_table_agent` | Captures readable table cells and page text. | Partial; chart values need digitisation. |
| Census screenshot | `misc data/agri census 2015-16.png` | `pending_image_ocr` | No OCR is run by this submission. | Pending; OCR dependency was unavailable here. |
| Raster maps | LULC map PDF and JPG | `skip_agent` | Records a deliberate skip. | Out of scope for raster interpretation. |

## Agent cards

### `pdf_table_agent`

- **Input:** a PDF from the source groups listed above.
- **Decision:** the manifest group selects the reader by a fixed rule.
- **Tool:** pdfplumber extracts the text layer and table cells.
- **Output:** `page_text` and `table_cell`; for the two Basic Statistics crop tables, `observation` rows include metric, crop, period, value, unit and page/table/row/column evidence.
- **Model:** none. The repeated table format and bilingual font labels are handled with explicit rules and a small decoder.
- **Limit:** cells from price and area/production PDFs are preserved but not yet converted into complete normalized crop records.

### `pdf_text_agent`

- **Input:** island profiles, food processing report and subsidy memorandum PDFs.
- **Decision:** a fixed source-group rule selects the text reader.
- **Tool:** pdfplumber extracts page text; a fixed keyword check retains exact lines containing agriculture terms and numbers.
- **Output:** page text plus `text_fact` evidence lines with document/page/run/agent.
- **Model:** none. It does not infer facts beyond the printed line.
- **Limit:** evidence lines are searchable captures, not a fully normalized knowledge base.

### Pending and skipped handlers

The image OCR and chart-digitisation handlers are not implemented. Their inputs remain in the manifest with explicit pending statuses. The two raster maps are mapped to an explicit skip decision. Therefore “nothing is unmapped” means every supplied file has an owner/status; it does not mean every file has been extracted.
