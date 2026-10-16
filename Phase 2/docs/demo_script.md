# Phase 2 demo runbook (about 20 minutes)

Run from the repo root with the venv: `PY=./.venv/bin/python`. Do the pre-flight the evening before.

## 0. Pre-flight
```bash
$PY -m pytest -q tests                                    # 27 tests, < 1 s
$PY scripts/run_pipeline.py --fresh --adapter adapters/TEAMID_AN_qlora_v1   # production DB (~25 min)
$PY scripts/eval_agents.py && $PY scripts/sample_queries.py && $PY scripts/make_eval_report.py
```
Keep `docs/evaluation.md` and `docs/source_agent_map.md` open in tabs.

## 1. Sources → agents (PDF §1), 2 min
Open `docs/source_agent_map.md` §1. Points to make:
* Every file is mapped, and D19/D20 are an explicit *skip* decision, not a gap.
* D18 is honestly *pending*.
* The grouping follows how a file must be read (format, encoding, layout), not its topic. G1 and G2 look alike but G2 hides Hindi in a legacy font.

## 2. Challenge + literature (PDF §2), 3 min
```bash
$PY -c "from agri.tools.krutidev import split_bilingual_label as s; print(s('Ukkfj;y Coconut (M/nuts)'))"
```
Show the tool-comparison table (`docs/challenge_literature.md`). Key line: *no general tool, Docling
included, recovers Kruti Dev Hindi (0/8); our decoder recovers 8/8*. Raster ruling: pdfplumber and PyMuPDF
find 0 tables, Docling gets 4/6 rows in 88 s, ours 6/6 in under a second. Be explicit that the encoding gap
is a *research/tooling* limitation, while the price-layout specialisation is *our implementation* limitation.

## 3. Individual agents with traces (PDF §3), 6 min
For each, run the trace and narrate *source input → agent decision → tool call → tool result → output*.
Purple lines (`by=model`) are LLM decisions; blue (`by=rule`) are code.
```bash
$PY scripts/show_trace.py D02 --records 3     # matrix: every column resolved by rules; C/Bay -> ZN_CAMPBELLBAY
$PY scripts/show_trace.py D07 --records 3     # rotated headers re-read; one column ("lle W") sent to the model
$PY scripts/show_trace.py D06 --records 3     # bilingual: Kruti decode, Hindi names saved as aliases
$PY scripts/show_trace.py D13 --records 3     # raster ruling detected; % variation cross-checks
$PY scripts/show_trace.py D10 --records 5     # island profiles: model extraction + groundedness gate
$PY scripts/show_trace.py D16 --records 3     # OCR: two dropped cells derived from row totals (error handling)
$PY scripts/show_trace.py D14 --records 5     # narrative facts with evidence; rejected facts counted
```
Difficult cases to point at:
* D11 misprinted year row (`year_row_mismatch → trust_title…`)
* D16 `ocr_missing_cell → derive_from_row_total`
* D10 model items rejected by the gate, then the teacher fills them

## 4. Orchestration (PDF §4), 3 min
Show the graph in `docs/orchestration.md`, then run a multi-agent batch live:
```bash
$PY scripts/run_pipeline.py --docs D07 D10 D13 D16
```
Explain:
* how agents are selected
* what passes between nodes (doc row, route, attempt, result summary, validation summary)
* retries: inside tools, inside agents, and across the graph
* completion: every run reaches a terminal status

**Unseen documents (gate requirement: 3 unseen, ≥ 1 non-English):**
```bash
$PY scripts/run_pipeline.py --adapter adapters/TEAMID_AN_qlora_v1 --files <instructor_file_1> <file_2> <file_3>
$PY scripts/show_trace.py U01
```
They are registered as U01…, routed from the fingerprint (model consulted only if ambiguous), extracted,
validated and loaded. A non-English (Hindi Kruti Dev) file goes to the bilingual agent automatically.
Rehearsal set: `D06`, `D10`, `D13`, which are never used in training.

## 5. Evaluation (PDF §5), 4 min
Open `docs/evaluation.md`:
* §2 **with vs without adapter** (held-out D10 / D02+D06).
* §2 **reworded-layout robustness**: the rule teacher collapses, while the models are measured on the same text.
* §3 Foundry-menu table: tool selection, trajectory (AgentEvals), tool input, task completion, adherence, groundedness, efficiency. Also say which evaluators were skipped and why.
* Direct value checks: 48 hand-read values.
* LangSmith: show the project if the key is configured (`scripts/langsmith_eval.py`); otherwise show the local traces.

## 6. Automation (PDF §6), 1 min
Read §4 of `evaluation.md`:
* inputs completed without intervention ÷ attempted
* the 0 manual interventions in the run
* retries and rejected model outputs
* remaining manual steps (Phase 1 download, URLs, gold review) and barriers (D18 charts)

## 7. Database (PDF §7), 2 min
```bash
sqlite3 db/TEAMID_AN_knowledgebase_v1.sqlite "SELECT * FROM v_provenance WHERE metric_id='production' AND commodity_id='coconut' AND location_id='AN' AND period_label='2025-26';"
sqlite3 db/TEAMID_AN_knowledgebase_v1.sqlite "SELECT metric_id, commodity_id, period_label, doc_a, value_a, doc_b, value_b, pct_diff FROM v_conflict LIMIT 5;"
```
Use `docs/schema.md` §5 to show agent output → schema. Use `docs/sample_queries.md` for the 10 queries.
