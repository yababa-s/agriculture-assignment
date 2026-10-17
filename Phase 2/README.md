# AgriAgent — Andaman & Nicobar Islands (Phase 2)

CS F/U 407 Artificial Intelligence, course project. This is an agentic system that reads the
team's Phase 1 corpus and fills a queryable, provenance-tracked agricultural knowledge base. The corpus
covers 20 government files: PDFs, bilingual Hindi tables in a legacy font, island profiles, monthly
price tables, budget memoranda, a screenshot, and LULC statistics.

**Results so far:** see [docs/interim_report.md](docs/interim_report.md) (numbers come from `eval/results/`).

## What is where

| Deliverable (methodology §5) | Location |
|---|---|
| Codebase | `agri/` (agents, tools, orchestrator, DB layer), `scripts/` (entry points) |
| Database + schema + data dictionary | `db/34_AN_knowledgebase_v1.sqlite`, [`agri/db/schema.sql`](agri/db/schema.sql), [`docs/schema.md`](docs/schema.md) |
| 10 sample queries with expected results | [`docs/sample_queries.md`](docs/sample_queries.md) (`scripts/sample_queries.py`) |
| Dataset/corpus manifest | [`data/manifest.csv`](data/manifest.csv): source, URL, collection date, language, licence, checksum |
| Agent & model | `agri/agents/*`, base model `mlx-community/Qwen2.5-3B-Instruct-4bit` (Qwen Research License: research/non-commercial use; see `adapters/README.md`), LoRA adapter in `adapters/` (adapter weights only) |
| Evaluation results | `eval/results/*.json`, summarised in [`docs/evaluation.md`](docs/evaluation.md) |
| Source → agent mapping | [`docs/source_agent_map.md`](docs/source_agent_map.md) |
| Challenge + literature + tool tests | [`docs/challenge_literature.md`](docs/challenge_literature.md) |
| Orchestration | [`docs/orchestration.md`](docs/orchestration.md) |
| Interim report | [`docs/interim_report.md`](docs/interim_report.md) |
| Logs | `logs/batch_*.json` (per batch), `logs/traces/*.jsonl` (per run), `logs/train_lora_*.log` |

## Large files (GitHub Release `phase2-v1`)

The database and adapter weights are not in the git history; they are attached to the release
[phase2-v1](https://github.com/yababa-s/agriculture-assignment/releases/tag/phase2-v1):

| File | Size | Unzip to |
|---|---|---|
| [34_AN_database_v1.zip](https://github.com/yababa-s/agriculture-assignment/releases/download/phase2-v1/34_AN_database_v1.zip) | 3.7 MB | `db/` |
| [34_AN_qlora_adapter_v1.zip](https://github.com/yababa-s/agriculture-assignment/releases/download/phase2-v1/34_AN_qlora_adapter_v1.zip) | 23 MB | `adapters/` |

The base model (`mlx-community/Qwen2.5-3B-Instruct-4bit`) downloads automatically from Hugging Face on first use.
The raw corpus is in `Phase 1/` of this repository.

## Setup (macOS, Apple Silicon)

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
export CORPUS_DIR="/path/to/AI Project Data Corpus"   # default: ../AI Project Data Corpus
export TEAM_ID=<your team id>                         # used in artifact names (34_AN_*)
```

The LLM runs locally through Apple MLX. No API key is needed, and no document leaves the machine.
LangSmith: put `LANGSMITH_API_KEY=...` in a local `.env` file (git-ignored). Tracing then goes to the project
`34_AN_agriagent`, and `scripts/langsmith_eval.py` records the base vs adapter experiments. Results are linked in `docs/evaluation.md`.

## Run

```bash
./.venv/bin/python scripts/run_pipeline.py --fresh --adapter adapters/34_AN_qlora_v1   # whole corpus
./.venv/bin/python scripts/run_pipeline.py --files ~/Downloads/new_document.pdf             # unseen document
./.venv/bin/python scripts/show_trace.py D07 --records 5                                  # demo trace
./.venv/bin/python scripts/eval_agents.py                                                  # agent evaluation
./.venv/bin/python scripts/eval_llm_tasks.py --label qlora_v1 --adapter adapters/34_AN_qlora_v1
```

`scripts/reproduce.sh` rebuilds every artifact from the raw corpus in order.

## Architecture in brief

```
file ─▶ router (manifest rule | fingerprint + LLM) ─▶ specialist agent ─▶ validator ─▶ loader ─▶ SQLite
                                                          ▲                  │
                                                          └── retry with ────┘
                                                              validator feedback
```

Seven extraction agents, one per source group:
* matrix tables
* bilingual Kruti Dev tables
* prices
* island profiles
* narrative
* OCR images
* LULC

They share the normalizer (gazetteer + aliases + LLM fallback) and the validator. Every decision is
logged as `by=model` or `by=rule`. Every stored number keeps its document, page, table, row label,
column label, raw cell text, run and agent.

## Repository layout

```
agri/
  config.py, sources.py, tracing.py
  db/            schema.sql, seed.py (gazetteer, commodities, metrics, units, aliases), db.py
  tools/         pdf_tools.py (grids, rotated headers, raster ruling), krutidev.py, parsing.py, lang.py
  llm/           client.py (MLX, adapters, JSON parsing)
  agents/        router, table_agents, table_mapping, price_agent, island_agent, narrative_agent,
                 image_agent, normalizer, validator, registry
  orchestrator/  graph.py (LangGraph)
scripts/         pipeline, datasets, training, evaluation, queries, traces
experiments/     tool_comparison.py (pdfplumber / PyMuPDF / Docling / ours)
data/            manifest.csv, splits/, gold/, training/
docs/            design, evaluation and report documents
eval/results/    machine-readable evaluation outputs
```

## Team 34

| Name | ID |
|---|---|
| Suyash Tripathi | 2025A7PS0663P |
| Abhineet Sharan | 2025A7PS0643P |
| Shikhar Singhania | 2024A7PS0561P |
