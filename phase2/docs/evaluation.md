# Evaluation results in plain language

## Latest local run

Run ID: `9e1171369c9e` (16 October 2026). The program processed the 17 supplied Phase 1 files in order.

| Measure | Result | Meaning |
|---|---:|---|
| Sources listed and found | 17/17 | All supplied files have a manifest entry and a route. |
| Final source statuses | 16 loaded, 1 partial, 0 pending, 0 skipped, 0 failed | The atlas chart is partial because the bars have no printed values. |
| Inputs loaded without manual intervention | 16/17 = 94.1% | This is the run's count, not a claim that all content was extracted. |
| Route checks | 17/17 | Every file reached its planned reader. |
| Tool sequence checks | 17/17 | Recorded tool calls matched the local fixed route plan. |
| Tool input checks | 17/17 | Each call used the expected source file path. |
| Structured observations | 21,158 | Includes table values, prices, census totals and five approximate chart readings. |
| Source value checks | 21,153/21,153 | Table/text/OCR values matched saved source text or cells; the five visual chart estimates are counted separately. |
| Checked Basic Statistics values | 4/4 | Four selected crop values matched the source. |
| Hindi label examples | 5/5 | Five selected Kruti Dev labels matched checked Hindi text. |
| Python checks | 5 passed | The bundled unit tests completed successfully. |
| SQLite integrity | `ok` | The delivered database passed SQLite's integrity check. |

The full per-file and per-source-group results are in `evaluation/latest_evaluation.json`. The run trace is in `logs/trace_9e1171369c9e.jsonl`.

## Evaluators selected for this workflow

The local checks cover source/agent selection (17/17), expected tool sequence (17/17), tool input path (17/17), task status, source grounding (21,153 observations), four checked numeric values, and five Hindi decoder examples. The report JSON also breaks tool-input and trajectory checks down by reader: image OCR 1/1, chart 1/1, map OCR 2/2, PDF tables 9/9, and PDF text 4/4. Source-group counts show all groups loaded except land use/land cover, where one of two sources is partial because of the chart.

The checked values and tool traces have different purposes. The 21,153 source matches check stored table/text/OCR evidence, while the four numeric and five Hindi examples use explicit checked references. Neither is a human review of every extracted number. The five chart estimates are excluded from exact-value checks.

We did not run answer helpfulness, response relevance or safety evaluators: this pipeline does not produce conversational LLM answers. Latency and token counts were not selected because they do not measure extraction quality here. The workflow records failures but has no automatic retry mechanism; source selection and downloading happen before execution. It recorded zero manual corrections and zero retries.

## What the AgentEvals/LangSmith score means

The user-provided LangSmith dashboard screenshot confirms a fresh experiment for dataset `agriculture-phase2-9e1171369c9e`: **17/17 runs** completed with **1.00 average strict trajectory match**. The experiment row is shortened in the screenshot (`phase2-agent-trajectories-485b...`). This means its recorded tool sequence matched the expected sequence. It is not an extraction accuracy score. The screenshot is saved at `logs/langsmith_experiment_9e1171369c9e.png`.

## How source checks work

- PDF table records are checked against their matching saved table cell.
- Text and OCR values are checked against source text or the OCR reading for the source cell.
- The four Basic Statistics examples compare saved values with checked references from the source PDF.
- The chart's five estimates are kept separate because they are read from bar heights, not printed numbers.

These checks do not prove every figure is correct. In particular, chart readings need human care, and a `loaded` status means the assigned reader finished its stated job, not that the entire source was normalized.

## What remains limited

- The atlas chart values are approximate pixel readings. Use the A&N-specific Phase 1 LULC data table for exact 2015-16 land-cover values.
- The two map files yield labels and legends, not GIS boundaries or area calculations.
- Some source tables are retained as raw cells; only selected data groups are normalized.
- The project does not train or fine-tune an LLM. The Hindi labels use a fixed Kruti Dev decoder.
- Source selection, downloading and reference-gold preparation happen before the automatic run.
