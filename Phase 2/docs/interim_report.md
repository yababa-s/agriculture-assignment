# Interim report: Phase 2
**Intelligent Agriculture Information System, Andaman & Nicobar Islands**
CS F/U 407 Artificial Intelligence · Team 34 · Phase 2 (data assimilation, working agents, database)

## 1. Summary

Phase 2 turns the Phase 1 corpus into a provenance-tracked knowledge base using an agentic pipeline.

* **Corpus:** 20 government files from DES A&N, Dept. of Agriculture, NRSC/Bhuvan and MoFPI.
* **Agents:** seven specialist extraction agents behind a router, sharing a normalizer and a validator, orchestrated with LangGraph.
* **Model:** a local Qwen2.5-3B model with a project LoRA adapter does the language work: reading prose profiles, interpreting unknown table headers, resolving unseen names, and routing ambiguous files.
* **Code:** handles bulk cell extraction, checks and provenance.

**Headline results (production batch `B20261016_035234` + island re-run `B20261016_041718`):**
* **Coverage:**
  * 20/20 files reached a terminal status with **0 manual interventions** (automation rate 1.0).
  * 15 files loaded; 4 bilingual files and D07 are partial (some columns unmapped); D18 is pending; D19/D20 are skipped by design.
  * **32,167** numeric facts and **74** evidence-backed text facts are in the database.
* **Accuracy:**
  * **Groundedness 100%:** every loaded number's printed text is found on its cited page.
  * **48/48** values read by eye from rendered pages match the database.
  * Routing is **20/20**.
* **LoRA adapter vs base model (held-out documents):**
  * island extraction F1 **0.27 → 0.94**
  * column mapping **0.03 → 0.64**
  * on a reworded, unseen layout, raw F1 **0.35 → 0.72**, where the regex baseline drops to 0.61.

## 2. Problem framing (from Phase 1, unchanged)

The goal is to answer spatial, temporal and provenance questions about A&N agriculture (production,
prices, inputs, land use, holdings, schemes) from official sources, every answer traceable to a page and cell.
Phase 2 builds and measures the extraction layer and the database; Phase 3 adds the query agent.

## 3. Sources and manifest

* `data/manifest.csv` records, per file:
  * source and portal
  * download URL from the Phase 1 inventory (DES ecostat portal, Bhuvan LULC viewer, MoFPI state profile)
  * collection date
  * languages and scripts (Kruti Dev detected automatically)
  * modality, pages, SHA-256
  * licence
* Licence position: DES and Agriculture Department portals state no licence, so their files are flagged *academic use only*. The MoFPI report is "all rights reserved", so it is used for academic extraction only and not redistributed. NRSC/Bhuvan publications may be used non-commercially with attribution.
* No personal data is extracted. The island profiles and machinery tables are aggregate counts; no farmer-level records exist in the corpus.

## 4. Sources → agents

The full map and agent cards are in [source_agent_map.md](source_agent_map.md). In brief:

| Group | Files | Agent | Hard part |
|---|---|---|---|
| G1 matrix tables | D01, D02, D07 | matrix_table_agent | merged/rotated headers, zone names, footnote units |
| G2 bilingual tables | D03–D06 | bilingual_table_agent | Hindi in Kruti Dev legacy font, 13 layouts per file |
| G3 price tables | D11–D13 | price_table_agent | rotated headers, raster ruling (2025), misprinted year rows |
| G4 island profiles | D08–D10 | island_profile_agent (LLM) | interleaved prose, synonyms, NIL values |
| G5 narrative | D14, D15 | narrative_agent (LLM facts) | segmentation, grounding of free text |
| G6 screenshot | D16 | image_table_agent | OCR, merged/dropped cells |
| G7 LULC | D17 (D18 pending) | lulc_agent | class hierarchy, other UTs |
| G8 raster maps | D19, D20 | skip (router) | out of scope by brief |

## 5. Challenge and literature

See [challenge_literature.md](challenge_literature.md). The focus is layout and encoding traps in government
PDFs, above all Hindi set in the Kruti Dev legacy font. No general tool we tested (pdfplumber, PyMuPDF,
Docling) recovers it; our glyph-map decoder recovers 8/8 test words. Raster-ruled tables, rotated headers
and OCR damage are handled by targeted tools and measured against values read from the pages.

## 6. Orchestration

Supervisor/router + per-document pipeline (route → extract → validate → retry? → load) in LangGraph.
Details, alternatives and failure handling: [orchestration.md](orchestration.md).

## 7. Evaluation and automation

Full tables are in [evaluation.md](evaluation.md), generated from `eval/results/`.

| Area | Result | Target |
|---|---|---|
| Direct value checks (hand-read) | 48/48 | ≥ 0.95 ✅ |
| Groundedness of loaded numbers | 1.00 (all agents) | ≥ 0.99 ✅ |
| Routing (deployed hybrid) | 20/20 on corpus; 0.95 when the model is asked on ambiguous files | ≥ 0.8 ✅ |
| Island extraction F1 (adapter, gated) | 0.935 (base 0.265) | ≥ 0.8 ✅ |
| Column mapping (adapter) | 0.635 (base 0.027) | ≥ 0.8 ❌, mitigated by id checks |
| JSON validity, island (adapter) | 0.61 strict, rest salvaged | ≥ 0.95 ❌, known loop issue |
| Automation (inputs without manual intervention / attempted) | 20/20 | ≥ 0.9 ✅ |
| LLM calls in the production run | 531; 157 model outputs rejected by gates | — |

* **Evaluators used (Foundry menu):** tool selection, trajectory (AgentEvals superset match), tool input accuracy, task completion, task adherence, groundedness, navigation efficiency.
* **Skipped, with reasons:** intent resolution, relevance/coherence/fluency and safety. They need natural-language answers, which arrive in Phase 3.
* **LangSmith:** held-out sets uploaded as datasets; base vs adapter recorded as 4 experiments; a 5-document pipeline batch traced end to end ([project](https://smith.langchain.com/o/b4705dec-ff81-4e43-839e-ba314f5e0268/projects/p/a4a2d107-08d5-4e06-af04-2f547794ef12)). Links in [evaluation.md](evaluation.md).

## 8. Database

SQLite star schema (fact table `observation` + lookup tables + provenance). The team's Production / Price /
Source design is preserved as `v_production`, `v_price`, `source`/`document`. Schema, identifiers, missing
values, duplicates and validation rules are in [schema.md](schema.md). The 10 sample queries with expected
results are in [sample_queries.md](sample_queries.md): spatial (Q1, Q2, Q6), temporal (Q3, Q4, Q8),
provenance (Q5), cross-source (Q7), census (Q9) and land use (Q10).

The database (`db/34_AN_knowledgebase_v1.sqlite`, 14.6 MB) holds:

| What | Count |
|---|---|
| Observations | 32,167, of which 2,264 are explicit missing values with a reason and 645 carry a validation warning |
| Commodities | 148 |
| Locations | 45 (UT, districts, tehsils, zones, islands, market) |
| Metrics | 39 |
| Periods | 2005-06 to 2025-26 |
| Text facts | 74 |
| Cross-source disagreements (`v_conflict`) | 341 |
| Hindi crop names | 40, filled automatically from decoded Kruti Dev labels |

## 9. Team 34

| Name | ID |
|---|---|
| Suyash Tripathi | 2025A7PS0663P |
| Abhineet Sharan | 2025A7PS0643P |
| Shikhar Singhania | 2024A7PS0561P |

## 10. Pending for Phase 3

1. **D18 atlas:** chart digitisation, or source the underlying NRSC state tables.
2. **D15 memoranda:** turn the subsidy line items (quantity × amount) into observations.
3. **Gazetteer:** add LGD codes to the location table.
4. **Instructor files:** widen layout coverage (more unseen price/table layouts) and retrain the adapter with any instructor files allowed into training.
5. **Query agent:** natural-language → SQL with provenance, including the 10-query acceptance test (2 spatial, 2 temporal, 1 provenance), using `document_chunk` for retrieval.
6. **Hindi names:** a few decoded names carry spacing artefacts from the PDF text layer (e.g. `सरसां े`), and one DES row prints तिलहन (oilseeds) next to "Seasam". Needs a Unicode normalisation pass plus manual review.
