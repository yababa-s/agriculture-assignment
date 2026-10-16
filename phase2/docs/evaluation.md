# Evaluation in plain language

The checked examples use only the supplied Basic Statistics PDFs. The 2023–24 file supplies the decoder development examples; the 2024–25 file is held out for the four numeric checks and two Hindi decoder checks. No test example is used as a training example.

## Checks included

1. **Coverage:** every manifest path exists and every file receives a route/status.
2. **Direct value check:** four page-1 values (Paddy area and production, Coconut area and production) are compared against the PDF.
3. **Hindi decoder check:** five Kruti Dev strings from the Basic Statistics PDFs are compared with checked Unicode labels.
4. **Trace checks:** each run records route, selected tool, counts, status, error if any, and database run ID. The local evaluation compares expected and actual routes/tool sequences, validates tool paths, and checks each normalized value against the matching raw source cell.
5. **Source/group summary:** counts are reported separately by reader and source group.

`evaluate.py` writes the actual counts and individual checked values to `evaluation/latest_evaluation.json`. Do not replace these with illustrative numbers in a presentation.

## Verified run in this package

On 16 October 2026, the bundled corpus was processed on Windows with pdfplumber and SQLite:

| Measure | Observed result |
|---|---:|
| Manifest entries and files found | 17/17 |
| Statuses | 12 loaded, 2 partial, 1 pending, 2 deliberate skips, 0 failed |
| Inputs fully handled without manual intervention (loaded or deliberate skip) | 14/17 = 82.4% |
| Manual interventions | 0 |
| Table cells preserved | 45,708 |
| Normalized Basic Statistics observations | 84 |
| Exact numeric checks | 4/4 |
| Hindi decoder checks | 5/5 |
| Unit tests | 4 passed |
| Routing / tool trajectory / input arguments | 17/17 routes, 17/17 trajectories, 14/14 tool inputs valid |
| Source groundedness | 84/84 normalized observations match their stored source cells |
| SQLite integrity / foreign-key check | `ok` / no violations |

Per source group and per reader counts are in the JSON results. “Loaded” means the reader completed its defined work; for the table reader, much of the corpus is preserved as raw cells rather than normalized crop facts. A partial, pending or skipped document is not counted as successfully extracted.

## What is not claimed

- No large language model was used, trained or fine-tuned. Hindi is a legacy-font decoding task here, so a fixed decoder is used. The methodology’s base-versus-adapter comparison is not applicable to this version; if the instructor requires that comparison as a gate, it remains work to do.
- AgentEvals and LangSmith were not installed/configured in the local runtime, so no hosted result is claimed. `phase2/hosted_eval.py` is an optional adapter that evaluates the saved tool trajectories with AgentEvals and sends run results to LangSmith when the packages and API key are available. The JSONL files are local traces, not LangSmith runs.
- The four numeric checks and five Hindi checks are a small held-out sample, not a validation of every source value.
- A high checked-value score on four examples does not mean all extracted rows are correct.

## Acceptance criteria for this package

| Check | Acceptance |
|---|---|
| Manifest coverage | All 17 bundled source files exist and have exactly one route/status. |
| Basic Statistics numeric checks | 4/4 exact matches against the cited source table. |
| Hindi label decoder | 5/5 held-out/development examples match the checked labels. |
| Provenance | Every normalized observation has document, page, table, row, column, agent and run. |
| Automation | Report inputs loaded or deliberately skipped without intervention ÷ attempted; partial, pending and failed are shown separately. |
