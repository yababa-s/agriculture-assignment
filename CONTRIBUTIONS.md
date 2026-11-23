# Contributions: Team 34 (Andaman & Nicobar Islands)

Roles follow the team charter: Source Lead, Data Engineering Lead, and Model Lead + Evaluation Lead (held by one
member, as the methodology allows for teams of 3). The same mapping is used in the report (Table 7), the slides
(slides 2 and 21), poster section 10 and the manual's document-control table. **Each member answers viva questions on
the parts they lead.**

| Member | Role | System components (lead) | Report | Slides | Poster | Manual / video |
|---|---|---|---|---|---|---|
| Suyash Tripathi (2025A7PS0663P) | Model Lead + Evaluation Lead | LangGraph orchestrator; LLM client (MLX + HF backends); island and narrative agents; LoRA adapters v1/v2 and training data; Query Agent planner; evaluation suite (field-level gold scoring, query evaluation, fine-tuning ladder); LangSmith | 4.1–4.3, 5, 6.1–6.4 | 7–9, 11–14 | 4, 6, 7 | 5; video segments "Processing" and "Querying" |
| Shikhar Singhania (2024A7PS0561P) | Source Lead | source inventory and manifest; Kruti Dev decoder and bilingual agent; tool comparison; degraded and fresh test documents; geospatial layer (boundaries, gazetteer, `build_geo.py`); maps and animations; query test set | 1–3, 6.5, 8 | 1–6, 17–22 | 1, 2, 8 | 1–2, 7–8; video "Introduction" and "Troubleshooting" |
| Abhineet Sharan (2025A7PS0643P) | Data Engineering Lead | schema v1/v2 and migration; normaliser and validator; typed read-only query tools; sample queries; reproducibility (requirements, `fetch_artifacts.py`, Makefile, CI, Docker); backup/restore and maintenance CLI; Streamlit app | 4.4–4.5, 6.6, 7, App. A | 10, 15–16 (live demo) | 3, 5, 9 | 3–4, 6; video "Installation" and "Maintenance" |

## Phase 3 work items and owners

| Work item | Owner | Where |
|---|---|---|
| Cross-platform install, artifact fetch with checksums, CI on 3 OSs, Docker | Abhineet | `requirements*.txt`, `scripts/fetch_artifacts.py`, `.github/workflows/`, `Dockerfile`, `Makefile` |
| Query agent, typed tools, page highlighter, app | Suyash (planner), Abhineet (tools, app) | `agri/query/`, `scripts/ask.py`, `app/` |
| Per-agent gold transcription and scoring | Shikhar (gold), Suyash (scoring) | `data/gold/field_gold.json`, `scripts/eval_fields.py` |
| Query dev/test sets | Shikhar (test set), Suyash (dev set, scorer) | `data/gold/queries*.json`, `scripts/eval_queries.py` |
| Adapter v2 (multi-task) and the fine-tuning ladder | Suyash | `scripts/build_datasets_v2.py`, `scripts/eval_llm_tasks.py --few-shot` |
| Geospatial layer, maps, animations, spatio-temporal analysis | Shikhar | `scripts/build_geo.py`, `scripts/make_figures.py`, `data/geo/` |
| Image-agent fixes found by the gold evaluation | Suyash | `agri/agents/image_agent.py` |
| Maintenance commands, scheduled workflow, source health check | Abhineet | `agri/ops.py`, `agri/cli.py`, `scripts/check_sources.py` |
| Fresh-file test set and licence review (D14 not redistributed) | Shikhar | `eval/results/phase3/surprise_p3.json`, `scripts/package_release.py` |
| Report, manual, slides, poster builders | all (by section, above) | `reports/` |

## A note on the commit history

The commits up to tag `phase2-v1` were pushed from one account (f20250663). The ownership table above is the team's
statement of who led each component, so the git author of a commit does not by itself show who did the work.

## Use of AI assistance

An AI coding assistant (Anthropic Claude) was used for code assistance, test writing, figure scripting and language
editing. All results are produced by the scripts in this repository from the team's data, and every member reviewed and
ran the code for their components. See the declaration in the report.
