# Progress log

| Date | Phase | What happened |
|---|---|---|
| 2026-09-07 → 09-12 | Setup | Team, state (Andaman & Nicobar Islands) and roles registered; repository created |
| 2026-09-17 → 09-26 | Phase 1 | Source discovery on the DES, Agriculture Department, MoFPI, NRSC and Bhuvan portals; 20 files downloaded (26 Sep); source inventory and proposed schema |
| 2026-10-14 → 10-18 | Phase 2 | Schema v1, 7 extraction agents + router, LangGraph orchestrator, Kruti Dev decoder, LoRA adapter v1, evaluation (value checks, LLM tasks, AgentEvals, LangSmith), unseen-document robustness tests; release `phase2-v1` |
| 2026-11-03 | Phase 2 → 3 | Router fix for Kruti Dev prose, narrative agent and decoder improvements (batches B20261103_*) |
| 2026-11-23 | Phase 3 | Cross-platform install (platform markers, HF/PEFT backend, adapter conversion), checksummed artifact fetch, corpus moved to `data/raw` |
| 2026-11-23 | Phase 3 | Query Agent (rule and LLM planners, 5 typed read-only tools, `--show-source` page highlighter), CLI and Streamlit app |
| 2026-11-23 | Phase 3 | Geospatial layer (Census 2011 / Survey of India boundaries, 53 geocoded places, schema v2 migration); maps and 3 animations |
| 2026-11-23 | Phase 3 | Per-agent field gold (405 new hand-transcribed facts); image-agent bugs found and fixed; query dev (30) and test (15) sets |
| 2026-11-23 | Phase 3 | Few-shot prompt baseline; adapter v2 (multi-task: +query planning, +routing); fresh-file test on 3 new DES documents |
| 2026-11-23 | Phase 3 | Maintenance CLI (backup/restore, add-source, licence check, log pruning), scheduled workflow, CI, Docker, 50 tests; fresh-clone dry run passed with no fixes |
| 2026-11-23 → 11-24 | Phase 3 | Report, manual, slides and poster built from the templates and `eval/results`; release `phase3-v1`; tag `phase3-submission` |
