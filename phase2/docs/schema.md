# Database and where the numbers came from

The database is SQLite, so it is one local file and needs no database server. The schema is in `db/schema.sql`; `run_pipeline.py --fresh` creates and fills it.

## Main tables

- `source_document`: one row per Phase 1 file, with source, type, language, path, checksum and extraction status.
- `extraction_run`: one row for a pipeline run, with start/end, attempted/completed counts and manual interventions.
- `page_text`: the text read from each page.
- `table_cell`: every non-empty table cell, preserving the page, table, row, column and original text.
- `observation`: selected numeric facts from the Basic Statistics whole-island crop table, including crop, metric, year, unit and source location.
- `text_fact`: exact evidence lines from profile/narrative pages.
- `agent_trace`: decisions, tool results and errors.
- `v_provenance`: a simple view joining each observation to its file, publisher, source type, page, cell, agent and run.

## Data rules

- A printed zero is stored as zero; an empty or unavailable cell does not become zero.
- Original strings are preserved in `value_raw` and `evidence`.
- A duplicate table cell or observation is ignored using a stable uniqueness key.
- The report records only values that parse as numbers. It does not silently convert measurement units.
- Table-cell capture and normalized observations are different things: the first preserves source structure; the second has a known metric/crop/year mapping.

## Example

The 2024–25 Basic Statistics PDF has the Paddy area `4365.2` on page 1. The table agent creates an `observation` row with metric `area_cultivated`, crop `Paddy`, period `2024-25`, unit `hectare`, and the original page/table/row/column. `v_provenance` joins that row to the PDF name and the run that extracted it. The automated check reads the same observation and compares it with a hand-checked reference value from that Phase 1 page.

Useful checks after a run:

```sql
SELECT metric, commodity, period, value, unit, file_name, page, row_no, col_no
FROM v_provenance
WHERE commodity IN ('Paddy', 'Coconut');

SELECT source_group, status, COUNT(*)
FROM source_document
GROUP BY source_group, status;
```
