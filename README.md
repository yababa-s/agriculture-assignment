# AgriAgent: Andaman & Nicobar Islands agricultural knowledge base (Team 34, Phase 3)

[![ci](https://github.com/yababa-s/agriculture-assignment/actions/workflows/ci.yml/badge.svg)](https://github.com/yababa-s/agriculture-assignment/actions/workflows/ci.yml)

CS F/U 407 Artificial Intelligence, course project. AgriAgent is an agentic system that reads 20 government agriculture
files of the Andaman & Nicobar Islands: zone-wise crop tables, bilingual Hindi tables in the legacy Kruti Dev font,
monthly price statements, island profiles, budget memoranda, a screenshot and land-use tables. It stores
**32,151 numbers in a SQLite knowledge base, each with its document, page, table, row, column, printed text, agent and run**.
A query agent then answers spatial, temporal, provenance and cross-source questions in English or Hindi, and can open the
source page with the cell highlighted.

| Headline result (held-out data) | Value |
|---|---|
| Field-level extraction, macro-F1 over 7 agents | **0.999** (n = 699 hand-transcribed facts), provenance accuracy 1.000 |
| Files processed without manual intervention | **20 / 20** |
| LoRA adapter vs base vs 3-shot prompt, island extraction F1 | 0.27 → 0.59 (prompt) → **0.94** (adapter), n = 294 |
| Query planning, untouched test set | base 0.60 · 3-shot 0.67 · **adapter v2 0.93** (n = 15) |
| Live demonstration queries | **10 / 10** (3 spatial, 3 temporal, 2 provenance, 1 cross-source, 1 Hindi) |
| Finding | North & Middle Andaman paddy **−41%** while arecanut area **+32%**, 2021-22 → 2025-26 (r = −0.83) |

Full write-up: `reports/out/34_AN_REPORT_v1.docx` (and PDF) · evaluation detail: [docs/evaluation_phase3.md](docs/evaluation_phase3.md)
· user manual: `reports/out/34_AN_MANUAL_v1.docx`.

---

## 1. Quick start (≤ 10 minutes, any OS, no API key or GPU)

```bash
git clone https://github.com/yababa-s/agriculture-assignment.git
cd agriculture-assignment
git checkout phase3-submission
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt        # Windows: .venv\Scripts\python
.venv/bin/python scripts/fetch_artifacts.py                 # database + adapters + corpus, SHA-256 verified (~150 MB)
.venv/bin/python -m pytest                                  # -> 50 passed
.venv/bin/python scripts/ask.py --no-llm "Which agri zone produced the most paddy in 2025-26?"
```

Expected answer: `Diglipur (agri zone) is highest with 6,941 t (71.5% of the total) [D02 p1]`.
Then try `--show-source` on a provenance question, or open the web app:
`.venv/bin/python -m streamlit run app/streamlit_app.py` → http://localhost:8501.
`make quickstart` runs the same steps on macOS and Linux.

## 2. Requirements

* Python 3.11–3.13 on macOS, Linux or Windows. CI tests a fresh clone on all three (`.github/workflows/ci.yml`).
* The LLM runs locally:
  * **Apple Silicon** with MLX (`mlx-lm`, installed automatically on M-series Macs).
  * **Elsewhere:** `pip install -r requirements-hf.txt` and `LLM_BACKEND=hf` (transformers + peft, CPU or CUDA).
  * **No model at all:** `--no-llm`, which uses the rules-only paths.
* Optional: `requirements-ocr.txt` (EasyOCR, for Hindi scans). A LangSmith API key is needed only for cloud tracing.
* Docker: `docker build -t agriagent . && docker run -p 8501:8501 agriagent` gives you the app, queries and rules-only pipeline.

## 3. Install and configure

Copy `.env.example` to `.env`; every variable has a default. The main ones:

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BACKEND` | `mlx` on Apple Silicon, else `none` | `mlx` \| `hf` \| `none` |
| `ADAPTER_PATH` | none | extraction adapter (`adapters/34_AN_qlora_v1`) |
| `QUERY_ADAPTER_PATH` | `adapters/34_AN_qlora_v2` | query-planning adapter |
| `DB_PATH` | `db/34_AN_knowledgebase_v2.sqlite` | knowledge base |
| `CORPUS_DIR` | `data/raw` | raw documents |
| `LANGSMITH_API_KEY` | unset | enables LangSmith tracing (project `34_AN_agriagent`) |

## 4. Artifacts (GitHub release `phase3-v1`)

Large files are not in git. `scripts/fetch_artifacts.py` downloads them and checks them against `artifacts.json`.

| File | Contents | Unpacks to |
|---|---|---|
| `34_AN_database_v2.zip` | knowledge base, schema v2 (3.9 MB zipped) | `db/` |
| `34_AN_qlora_adapters_v2.zip` | LoRA adapter weights v1 + v2 (MLX and PEFT formats), **no base model** | `adapters/` |
| `34_AN_corpus_v1.zip` | 19 of 20 corpus files (D14 not redistributable: see `release/CORPUS_EXCLUDED.txt`) | `data/raw/` |

Offline: put the zips in `release/` and run `python scripts/fetch_artifacts.py --from-dir release/`.
The base model `mlx-community/Qwen2.5-3B-Instruct-4bit` (or `Qwen/Qwen2.5-3B-Instruct` for `hf`) downloads from Hugging Face on first use.

## 5. Usage

```bash
python scripts/ask.py "How did paddy production in the UT change from 2019-20 to 2025-26?"     # model planner (hybrid)
python scripts/ask.py --no-llm --explain "Which islands within 60 km of Port Blair have the most farmers?"
python scripts/ask.py --show-source "Which source and page did the 2025-26 coconut production figure for A&N come from?"
python scripts/ask.py --demo                                   # the 10 live demonstration queries
python scripts/run_pipeline.py --files ~/Downloads/new.pdf     # process an unseen document
python scripts/run_pipeline.py --docs D02 --replace --no-llm   # re-extract one corpus file
python scripts/show_trace.py D07 --records 5                   # see every decision and tool call
python -m agri.cli status | backup | restore FILE | check-licenses | add-source FILE ... | prune-logs
```

Expected answers for the 10 demo queries: [docs/demo_queries.md](docs/demo_queries.md).
Ten SQL sample queries with expected results: [docs/sample_queries.md](docs/sample_queries.md).

## 6. Reproduce all results

| Command | Rebuilds |
|---|---|
| `bash scripts/reproduce.sh` | manifest → DB → datasets → adapter v1 → LLM evaluation → production run → agent evaluation (~2 h, Apple Silicon) |
| `python scripts/build_datasets_v2.py && DATA=data/training_v2 ADAPTER=adapters/34_AN_qlora_v2 ITERS=450 ./scripts/train_lora.sh` | adapter v2 (~90 min) |
| `python scripts/eval_fields.py` | per-agent P/R/F1 + 95% CI → `eval/results/phase3/field_eval_v2.json` |
| `python scripts/eval_queries.py --label rules --planner rules` (also `--set test`, `--planner model --adapter …`) | query evaluation |
| `python scripts/eval_llm_tasks.py --label qlora_v2 --adapter adapters/34_AN_qlora_v2` and `--few-shot 2` | the fine-tuning ladder |
| `python scripts/make_figures.py && python scripts/make_eval_figures.py && python scripts/make_diagrams.py` | every figure and animation in `figures/` |
| `python reports/build_report.py`, `build_manual.py`, `build_slides.py`, `build_poster.py` | the four documents, from the templates and `eval/results` |

## 7. Evaluation summary

| Agent (held-out region) | n | P | R | F1 |
|---|---|---|---|---|
| matrix_table (D02 p1) | 80 | 1.000 | 1.000 | 1.000 |
| bilingual_table, Hindi (D06 p2) | 87 | 1.000 | 1.000 | 1.000 |
| price_table (D13 p11) | 70 | 1.000 | 1.000 | 1.000 |
| island_profile (D10) | 294 | 0.997 | 1.000 | 0.998 |
| narrative (D15) | 12 | 1.000 | 1.000 | 1.000 |
| image_table, OCR (D16) | 128 | 1.000 | 0.984 | 0.992 |
| lulc (D17) | 28 | 1.000 | 1.000 | 1.000 |
| **macro-average** | 699 | 1.000 | 0.998 | **0.999** |

Degraded inputs remain hard: scans and photos reach recall 0.10–0.52. Fresh files with **new** layouts are mis-mapped:
5/15 and 0/15 correct on hand-checked samples. All of this is reported in [docs/evaluation_phase3.md](docs/evaluation_phase3.md).

## 8. Data, manifest and licences

* `data/manifest.csv` records, for each of the 20 files: publisher, portal and download URL, collection date, period, geography, modality, pages, language and script, legacy-font flag, SHA-256 and licence.
* Run `python -m agri.cli check-licenses` before adding or sharing data.
* 15 files have no stated licence and are **flagged academic use only**. NRSC/Bhuvan files are used under their non-commercial terms. D14 (MoFPI) is not redistributed.
* No personal or beneficiary-level data is held.
* Map boundaries: Census 2011 / Survey of India via DataMeet (see [docs/geo.md](docs/geo.md)). Maps of India use the Survey of India boundary.

## 9. Model and adapters

* Base model: `Qwen2.5-3B-Instruct`, 4-bit, running locally. It is under the **Qwen Research License** (research and non-commercial use), so only adapter weights are distributed.
* **v1** is LoRA r = 8 with scale 20 on 16 layers, trained for 250 iterations on 84 examples. It is used for extraction.
* **v2** adds 180 query-planning and 18 routing examples and is trained for 450 iterations. It is used for query planning.
* Training data comes from TRAIN documents only (`data/splits/splits.json`). Contamination reports are in `scripts/build_datasets.py` and `data/training_v2/contamination_report.json`.
* Details: [adapters/README.md](adapters/README.md).

## 10. Repository layout

| Template component | Location |
|---|---|
| Orchestrator | `agri/orchestrator/graph.py` (LangGraph) |
| Agents | `agri/agents/` (router, 7 extraction agents, normaliser, validator) |
| Tools | `agri/tools/` (PDF grid, Kruti Dev decoder, OCR, parsing) |
| Model client | `agri/llm/client.py` (MLX / HF / none); adapters in `adapters/` |
| Database | `agri/db/` (schema.sql v2, migration, loader); dump in `db/` |
| Query interface | `agri/query/` (agent, typed read-only tools, page renderer), `scripts/ask.py`, `app/streamlit_app.py` |
| Configuration | `agri/config.py` + `.env` (no secrets or paths in code) |
| Maintenance | `agri/ops.py`, `agri/cli.py` (`python -m agri.cli …`) |
| Data | `data/` (manifest, splits, gold sets, training data, geo layer, test documents) |
| Evaluation | `scripts/eval_*.py`, `experiments/`, `eval/results/` |
| Documentation | `docs/` (schema, evaluation, geo, demo queries, scripts), `reports/` (document builders + outputs) |
| Tests and CI | `tests/`, `.github/workflows/` |
| Phase 1 deliverables | `Phase 1/` (source inventory and the files collected in Phase 1; Phase 2 is at tag `phase2-v1`) |

## 11. Maintenance

The user manual, Section 6, covers adding a source, updating an agent or adapter, scheduled runs, backup and restore,
logs, and licence checks. In short: `python -m agri.cli add-source …` → `run_pipeline --docs Dxx` → add gold → `eval_fields`.

## 12. Team and contributions

| Name | ID | Role |
|---|---|---|
| Suyash Tripathi | 2025A7PS0663P | Model Lead + Evaluation Lead |
| Shikhar Singhania | 2024A7PS0561P | Source Lead |
| Abhineet Sharan | 2025A7PS0643P | Data Engineering Lead |

Who built what: [CONTRIBUTIONS.md](CONTRIBUTIONS.md). Progress log: [docs/progress_log.md](docs/progress_log.md).

## 13. Licence

Code: MIT (see `LICENSE`). Data and model terms: Section 8 and Section 9.

## 14. Submission artifacts (tag `phase3-submission`)

`34_AN_REPORT_v1.docx/.pdf` · `34_AN_PRESENTATION_v1.pptx` · `34_AN_POSTER_v1.pptx/.pdf` · `34_AN_MANUAL_v1.docx/.pdf` ·
`34_AN_MANUAL_VIDEO_v1.mp4` (link in the manual) · release `phase3-v1` (database, adapters, corpus).
