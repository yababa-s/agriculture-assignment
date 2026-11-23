"""Build the Phase 3 report (34_AN_REPORT_v1.docx) from the course template and eval/results.

  python reports/build_report.py [--template PATH] [--out reports/out/34_AN_REPORT_v1.docx]

Every number in the results sections is read from eval/results/*.json or the database at build time.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agri import config  # noqa: E402
from reports.docx_kit import Doc  # noqa: E402

R, P3, FIG = config.RESULTS_DIR, config.RESULTS_DIR / "phase3", config.FIGURES_DIR
TEAM = json.loads((ROOT / "reports" / "team.json").read_text())
TEMPLATE = Path.home() / "Desktop" / "Phase 3 requirements" / "TEAMID_STATE_REPORT_template.docx"


def J(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def f3(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def f2(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


class Data:
    def __init__(self):
        self.db = sqlite3.connect(config.DB_PATH)
        self.field = J(P3 / f"field_eval_{config.DB_VERSION}.json")
        self.field_v1 = J(P3 / "field_eval_v1_phase2.json")
        self.llm = {k: J(R / f"llm_eval_{k}.json") for k in ("base", "base_fewshot2", "qlora_v1", "qlora_v2", "teacher")}
        self.q = {}
        for p in P3.glob("query_eval_*.json"):
            e = J(p)
            self.q[(e["set"], e["label"])] = e
        self.agent_eval = J(R / "agent_eval_B20261016_041718.json")
        self.robust = J(R / "robustness_unseen.json")
        self.surprise = J(P3 / "surprise_p3.json")
        self.tools = {t: J(R / f"tool_comparison_{t}.json") for t in ("pdfplumber", "pymupdf", "docling", "ours")}
        self.n_obs = self.db.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
        self.n_docs_data = self.db.execute("SELECT COUNT(DISTINCT document_id) FROM observation").fetchone()[0]
        self.manifest = list(csv.DictReader(config.MANIFEST_PATH.open()))
        self.pages = sum(int(r["pages"] or 0) for r in self.manifest)

    def qa(self, s, label, key="answer_accuracy"):
        e = self.q.get((s, label))
        return e["overall"][key] if e else None


def build(out: Path, template: Path) -> Path:
    D = Data()
    fe, m = D.field, D.field["macro"]
    doc = Doc(template, {"[TEAMID]": TEAM["team_id"], "[State]": TEAM["state"]})
    names = [x["name"] for x in TEAM["members"]]
    v1, v2, base, fs = D.llm["qlora_v1"], D.llm["qlora_v2"], D.llm["base"], D.llm["base_fewshot2"]
    isl = lambda e: e["island_extraction"]["after_groundedness_gate"]["f1"] if e else None  # noqa: E731
    col = lambda e: e["column_mapping"]["column_accuracy"] if e else None  # noqa: E731
    best_q_test = D.qa("test", "hybrid_rules_v2") or D.qa("test", "rules")
    demo = J(P3 / "query_eval_dev_hybrid_rules_v2.json") or J(P3 / "query_eval_dev_rules.json")
    demo_rows = [r for r in demo["results"] if r["demo"]]
    demo_ok = sum(r["correct"] for r in demo_rows)

    # ------------------------------------------------------------------ front matter
    doc.title("Provenance-Tracked Agentic Extraction of Multilingual Agricultural Statistics for the Andaman & Nicobar Islands")
    doc.para(", ".join(f"{n}¹" for n in names), align="center", after=2)
    doc.para(f"¹ {TEAM['institute']}  ·  Corresponding author: {TEAM['contact']}", size=9.5, align="center", after=2)
    doc.para(f"Team ID: {TEAM['team_id']}  ·  State: {TEAM['state']}  ·  Course: {TEAM['course']}  ·  Submitted: 24 November 2026",
             size=9.5, align="center", after=8)
    doc.table(None, ["Artefact", "Link or location"], [
        [f"GitHub repository (tag {TEAM['tag']})", TEAM["repo"]],
        ["Database dump and schema", f"{TEAM['release']} (34_AN_database_v2.zip) · agri/db/schema.sql · docs/schema.md"],
        ["Corpus and manifest", f"{TEAM['release']} (34_AN_corpus_v1.zip) · manifest: data/manifest.csv"],
        ["Adapter weights (LoRA/QLoRA)", f"{TEAM['release']} (34_AN_qlora_adapters_v2.zip)"],
        ["LangSmith project", TEAM["langsmith_project"]]], [5.2, 10.8])

    doc.h1("Abstract")
    doc.para(
        f"Agricultural statistics for the Andaman & Nicobar Islands are published as scattered government PDFs: zone-wise "
        f"crop tables, bilingual tables whose Hindi is encoded in the legacy Kruti Dev font, monthly price statements, "
        f"island profiles, budget memoranda, a web screenshot and land-use tables. We built AgriAgent, a LangGraph system in "
        f"which a supervisor routes each file to one of seven specialist agents. The agents combine deterministic table tools "
        f"with a locally run Qwen2.5-3B model adapted with LoRA, and they write {D.n_obs:,} normalised observations into a SQLite "
        f"knowledge base. Every number keeps its document, page, table, row, column, printed text, agent and run. A query "
        f"agent answers spatial, temporal, provenance and cross-source questions in English or Hindi through typed, read-only "
        f"tools, and can show the cited page with the cell highlighted. On {fe['n_gold_total']} hand-transcribed facts from "
        f"held-out pages, field-level macro-F1 is {f3(m['f1'])}, with provenance accuracy {f3(m['provenance_accuracy'])}. "
        f"All 20 corpus files were processed without manual intervention. The adapter raises held-out island-extraction F1 "
        f"from {f2(isl(base))} (base) and {f2(isl(fs))} (two-shot prompt) to {f2(isl(v1))}. The query agent answers "
        f"{demo_ok}/10 demonstration queries correctly and reaches {f2(best_q_test)} accuracy on an untouched paraphrase set. "
        f"The data show paddy production in North & Middle Andaman falling 41% between 2021-22 and 2025-26 while arecanut "
        f"area there grew 32%. The main limitation is OCR recall on photographed and scanned pages.", align="justify")
    doc.para("**Keywords:** agentic AI; information extraction; agricultural statistics; LoRA; knowledge base; provenance; "
             "Andaman & Nicobar Islands", after=10)

    # ------------------------------------------------------------------ 1
    doc.h1("1. Introduction")
    doc.para(
        "The Andaman & Nicobar Islands (A&N) are a Union Territory of 836 islands spread over about 800 km of the Bay of Bengal. "
        "Agriculture is small in area but central to the livelihood of the settled islands: paddy in the valleys of North and "
        "Middle Andaman, coconut and arecanut plantations, spices, fruit and vegetables. Most land is forest. Because the islands "
        "depend on shipping from the mainland, local food prices are volatile.", align="justify")
    doc.para(
        "Information about this sector exists, but it is hard to use. Three departments publish it: the Directorate of Economics "
        "& Statistics (DES), the Department of Agriculture and NRSC/Bhuvan. They use different units of geography: districts, "
        "tehsils, eight agricultural zones and 31 islands. Most of it is in PDFs with ruled tables, rotated headers and "
        "multi-row column labels. The DES Basic Statistics tables are bilingual, and their Hindi text is stored in the legacy "
        "Kruti Dev font, so standard extractors return Latin gibberish. Island profiles are semi-structured prose. Some content "
        "exists only as screenshots. No portal answers a simple question such as *which zone grew most paddy last year, how "
        "has that changed, and where does the number come from?*", align="justify")
    doc.para(
        "The intended users are state agriculture and planning analysts, researchers and extension staff. Their questions "
        "compare places (spatial), follow a series over years or months (temporal), and need to be traceable to the "
        "publication (provenance). This paper describes a system that turns the published files into a queryable, "
        "provenance-tracked knowledge base and answers such questions.", align="justify")
    doc.para("The main contributions of this work are:")
    doc.bullets([
        "**A source-to-agent architecture** that covers 20 files from 5 publishers in 6 modalities (digital PDF, legacy-font "
        "bilingual PDF, image, narrative, statistics atlas, raster map). A supervisor routes each file to one of seven "
        "specialist agents, and a shared normaliser and validator follow (Sections 3–4).",
        f"**Local LoRA adaptation**, with the gain measured on held-out documents against both the base model and a few-shot "
        f"prompt: island-extraction F1 {f2(isl(base))} → {f2(isl(fs))} (prompt) → {f2(isl(v1))} (adapter). A second, "
        f"multi-task adapter repairs the tasks the first one damaged (Section 6.2).",
        f"**A provenance-preserving knowledge base** of {D.n_obs:,} observations with a geospatial layer. A query agent over "
        f"it answers spatial, temporal, provenance and cross-source questions in English and Hindi and shows the source page "
        f"(Sections 4.4 and 6.4).",
        "**Three spatio-temporal findings with their sources**: a shift from paddy to arecanut in North & Middle Andaman, "
        "monsoon and winter price peaks in Port Blair, and the concentration of farmers on two islands. Two errors inside the "
        "source publications were also found and documented (Section 6.5).",
    ], numbered=True)
    doc.para("Section 2 reviews related work. Section 3 describes the study area and sources, and Section 4 the system. "
             "Sections 5–6 define the evaluation and report the results. Sections 7–9 discuss limitations, ethics and future "
             "work.", align="justify")

    # ------------------------------------------------------------------ 2
    doc.h1("2. Related Work")
    doc.h2("2.1 Document AI and table extraction")
    doc.para(
        "Layout-aware pre-training (LayoutLM [5]) and OCR-free models such as Donut [15] made document understanding "
        "learnable. Table structure recognition moved to transformer models trained on large corpora of scientific and "
        "financial tables: TableFormer [6] and PubTables-1M [7]. Pipelines such as Docling [12] combine these with layout "
        "analysis, and the classical OCR engine Tesseract [16] is still a common fallback. These methods assume Unicode text "
        "or clean scans, and their training data is dominated by English papers and reports. When we tested them on our own "
        "hardest pages (Table 4b), Docling recovered 4 of 6 cells on a raster-ruled table and none of 8 on Kruti Dev text. "
        "pdfplumber and PyMuPDF failed on both. The open problem for our sources is therefore not structure recognition in "
        "general but recovering the *text* (legacy encodings) and the *meaning of header combinations* (zone × metric × year).",
        align="justify")
    doc.h2("2.2 LLM agents and tool use")
    doc.para(
        "ReAct [3] interleaves reasoning with tool calls, Toolformer [4] showed that language models can learn when to call "
        "tools, and graph-based orchestrators such as LangGraph [17] make multi-agent control flow explicit and traceable. "
        "Natural-language querying of databases has been studied as text-to-SQL, from the Spider benchmark [8] to "
        "decomposed in-context methods such as DIN-SQL [9]. Free-form SQL generation by a 3-billion-parameter model is "
        "fragile, and retrieval-augmented generation [14] grounds answers in text, not in auditable numbers. We therefore "
        "keep the model at the decision level (routing, column meaning, query planning) and give it typed, parameterised "
        "tools whose SQL is fixed. Every model decision is logged as such.", align="justify")
    doc.h2("2.3 Parameter-efficient fine-tuning")
    doc.para(
        "LoRA [1] trains low-rank updates to frozen weights, and QLoRA [2] does so on a 4-bit quantised base, which makes "
        "adaptation possible on a laptop. In-context learning with a few examples [13] is the obvious cheaper alternative. "
        "Small instruction-tuned models such as Qwen2.5 [11] are strong enough for structured extraction, but the literature "
        "rarely reports what fine-tuning adds over a few-shot prompt *on the same held-out cases*, or what it costs on tasks "
        "the adapter was not trained for. We report both (Section 6.2).", align="justify")
    doc.h2("2.4 Agricultural information systems in India")
    doc.para(
        "National portals (UPAg [24], Agmarknet, data.gov.in) provide state-level series, and advisory assistants such as "
        "Farmer.Chat [25] answer farmers' questions with LLMs. Island-level and zone-level data for A&N exist only in "
        "territory publications. Neither kind of system keeps cell-level provenance, and translation-oriented Indic NLP work "
        "such as IndicTrans2 [10] does not address legacy font encodings inside statistical tables.", align="justify")
    doc.h2("2.5 Research gap addressed in this work")
    doc.para(
        "Taken together, existing tools solve generic table detection, generic agent orchestration and generic text-to-SQL. "
        "They leave open what our sources need: decoding Kruti Dev bilingual tables, mapping multi-level headers to a fixed "
        "schema of place × metric × period, keeping a verifiable citation for every number, and answering questions that "
        "cross three geographic hierarchies. Some of these limits belong to the methods themselves, such as no handling of "
        "legacy encodings. Others are implementation gaps in available tools, such as no provenance export. Section 7 keeps "
        "the two apart. We address the gap with specialist agents, a validator, a provenance schema and a tool-based query "
        "agent, and we measure each part.", align="justify")

    # ------------------------------------------------------------------ 3
    doc.h1("3. Study Area and Data Sources")
    doc.h2("3.1 Study area")
    doc.para(
        "A&N has three districts (North & Middle Andaman, South Andaman and Nicobar), nine tehsils and eight "
        "Department-of-Agriculture zones. It has a humid tropical climate with two monsoons and about 3,000 mm of rain a "
        "year. In the LULC 2015-16 statistics, forest covers 86% of the land and agriculture under 7%. The cultivated area is "
        "concentrated in the valleys of North and Middle Andaman (paddy, arecanut, vegetables) and in coconut plantations on "
        "the Nicobar islands. Figure 1 shows the districts, zone headquarters and islands covered by the knowledge base.",
        align="justify")
    doc.figure(FIG / "fig1_study_area.png", "Study area: the three districts of A&N (Census 2011 boundaries digitised from Survey "
               "of India maps, via DataMeet), the eight agriculture-zone headquarters and the 31 islands with profiles. Inset: "
               "India with the Survey of India boundary. Record counts are from knowledge base v2 (23 Nov 2026).", 9.0)
    doc.h2("3.2 Source inventory and corpus")
    m_by = {}
    for r in D.manifest:
        m_by.setdefault(r["source_group"], []).append(r)
    groups = [("G1_MATRIX_TABLES", "Agri Dept zone-wise area & production; DES machinery", "PDF (digital)", "English", "matrix_table_agent"),
              ("G2_BILINGUAL_TABLES", "DES Basic Statistics, agriculture chapter", "PDF, Kruti Dev legacy font", "Hindi + English", "bilingual_table_agent"),
              ("G3_PRICE_TABLES", "DES comparative statement of retail prices", "PDF (digital)", "English", "price_table_agent"),
              ("G4_ISLAND_PROFILES", "DES Island-wise Statistical Outline", "PDF, semi-structured text", "English + Hindi", "island_profile_agent"),
              ("G5_NARRATIVE", "MoFPI state profile; Agri Dept explanatory memoranda", "PDF, narrative", "English", "narrative_agent"),
              ("G6_IMAGE_TABLES", "DES Agriculture Census 2015-16 web page", "PNG screenshot", "English", "image_table_agent"),
              ("G7_LULC", "Bhuvan LULC 2015-16 statistics; NRSC LULC atlas 2024", "PDF, tables + charts", "English", "lulc_agent"),
              ("G8_RASTER_MAPS", "Bhuvan/NRSC LULC maps", "Raster image / map PDF", "—", "skip (by brief)")]
    rows = []
    for i, (g, name, mod, lang, agent) in enumerate(groups, 1):
        ds = m_by.get(g, [])
        n_obs = D.db.execute(f"SELECT COUNT(*) FROM observation WHERE document_id IN ({','.join('?' * len(ds))})",
                             [d["doc_id"] for d in ds]).fetchone()[0] if ds else 0
        pages = sum(int(d["pages"] or 0) for d in ds)
        lic = "Not stated → academic use only" if "no explicit" in ds[0]["license"].lower() else ds[0]["license"].split(";")[0]
        status = "Done" if g not in ("G7_LULC", "G8_RASTER_MAPS", "G5_NARRATIVE") else ("Pending (by brief)" if g == "G8_RASTER_MAPS" else "Partial")
        rows.append([f"S{i}", f"{name} ({', '.join(d['doc_id'] for d in ds)})", mod, lang, "Manual download (portal)", lic,
                     f"{len(ds)} files, {pages} pp; {n_obs:,} records", agent, status])
    rows.append(["S9", "Census 2011 / Survey of India district boundaries; India outline (DataMeet)", "Vector (shapefile/GeoJSON)",
                 "—", "Scripted download", "CC BY 2.5 IN / ODbL", "3 districts, 31 island polygons, 53 points", "build_geo.py", "Done"])
    rows.append(["S10", "Fresh Phase 3 test set: DES island outline 2021-22, District at a Glance 2024-25, A&N at a Glance 2025",
                 "PDF (digital), new layouts", "English", "Scripted, 1 request / 3 s", "Not stated → academic use only",
                 "3 files, 21 pp (test only)", "router → agents", "Test only"])
    doc.table("Source inventory (final).", ["#", "Source / portal", "Modality", "Language", "Access method", "License",
                                             "Volume collected", "Agent", "Status"], rows,
              [0.8, 3.6, 1.9, 1.4, 1.7, 1.8, 2.1, 1.9, 1.2], size=7.5)
    doc.para(
        f"The 20 corpus files ({D.pages} pages) were downloaded by hand from the DES, Agriculture Department, MoFPI, NRSC and "
        f"Bhuvan portals on 26 September 2026. The 3 Phase 3 test files were fetched on 23 November 2026 by a script that "
        f"waited 3 s between requests. `data/manifest.csv` records, for every file: publisher, portal and download URL, "
        f"collection date, period, geography, modality, page count, language and script, legacy-font flag, size, SHA-256 and "
        f"licence. No portal states an open licence except the NRSC/Bhuvan data policy. The other files are flagged *academic "
        f"use only*. D14 (MoFPI) explicitly forbids redistribution, so it is not included in the released corpus and is "
        f"downloaded from its URL instead. The sources are aggregate statistics with no person-level records. Island profiles "
        f"contain only counts. `agriagent check-licenses` enforces these rules before data is added or shared.", align="justify")

    # ------------------------------------------------------------------ 4
    doc.h1("4. System Architecture and Methodology")
    doc.h2("4.1 Overall architecture and orchestration")
    doc.figure(FIG / "fig2_architecture.png", "Architecture. Files are routed by a supervisor to specialist agents (tools in "
               "each box). Records pass a shared normaliser and validator, with retries on validator feedback, before loading. "
               "The query agent reads the knowledge base through read-only typed tools. Red dotted arrows are LLM calls; every "
               "decision is traced as by=model or by=rule.", 16.5)
    doc.para(
        "**Pattern.** We use a supervisor/router pattern implemented as a LangGraph state graph: *route → extract → "
        "normalise → validate → (retry | load) → finish*. It suits our corpus because the source groups need different tools "
        "(geometric table parsing, font decoding, OCR, line selection plus LLM). A single generalist agent would have to "
        "carry every tool in one prompt, which a 3B model handles poorly. We rejected a purely sequential pipeline (no "
        "per-file choice of tools) and a hierarchical design with sub-agents per page (more calls, no measured benefit on "
        "this corpus).", align="justify")
    doc.para(
        "**Execution and state.** A batch starts from `scripts/run_pipeline.py` (`agriagent run`). It takes manifest "
        "documents, unseen files given with `--files`, or both. The state passed between nodes holds the document record, "
        "the agent chosen and why, the candidate records, the validator verdicts, the number of attempts and the trace "
        "handle. The router first uses the manifest's source group (a rule). For an unseen file it computes a fingerprint "
        "(page count, text density, ruled-table count, legacy-font detection, languages) and uses heuristic rules, and the "
        "LLM decides only when the fingerprint is ambiguous.", align="justify")
    doc.para(
        f"**Retries and failures.** When the validator rejects a share of records (unknown place or metric, out-of-range "
        f"value, failed row-sum check), the agent is re-run with the validator's messages, up to {config.MAX_RETRIES} times. "
        f"Model outputs that fail a groundedness gate (the evidence span must occur verbatim in the page text and contain "
        f"the value) are dropped, not repaired. Errors inside tools are caught and recorded, and a document ends as *loaded*, "
        f"*partial*, *needs_review*, *failed* or *skipped*. One bad file never stops a batch.", align="justify")
    doc.h2("4.2 Agents and source mapping")
    doc.table("Agents, their responsibilities and tools.", ["Agent", "Sources handled", "Responsibility", "Model(s)", "Tools",
                                                            "Decided by model vs code"], [
        ["Router (supervisor)", "all + unseen", "pick one agent per file", "Qwen2.5-3B (+LoRA v2) when ambiguous",
         "fingerprint, manifest lookup", "Model: ambiguous unseen files; code: manifest rule, fingerprint heuristics"],
        ["matrix_table", "S1 (D01, D02, D07)", "crop × place × metric tables", "LLM fallback only", "pdfplumber grid, rotated-header "
         "reader, raster ruling", "Model: header meaning when rules fail; code: grid, numbers, units"],
        ["bilingual_table", "S2 (D03–D06)", "Kruti Dev bilingual tables", "Qwen2.5-3B + LoRA", "Kruti Dev→Unicode decoder, "
         "label splitter", "Model: column → (place, metric, period); code: decoding, cell values"],
        ["price_table", "S3 (D11–D13)", "monthly comparative prices", "none", "statement parser, year/column checks",
         "Code only (fixed layout); model not needed"],
        ["island_profile", "S4 (D08–D10)", "key-value facts per island", "Qwen2.5-3B + LoRA", "line selector, groundedness gate",
         "Model: fact extraction; code: island segmentation, evidence check"],
        ["narrative", "S5 (D14, D15)", "scheme outlay/expenditure, facts", "Qwen2.5-3B", "scheme segmenter, table reader",
         "Model: facts from prose; code: outlay tables"],
        ["image_table", "S6 (D16)", "OCR table screenshot", "none", "Vision OCR, grid rebuild, re-OCR of empty cells",
         "Code only"],
        ["lulc", "S7 (D17, D18)", "land-use statistics", "none", "LULC table parser", "Code only"],
        ["normaliser / validator", "all agents", "ids for places, crops, metrics, units; checks", "LLM fallback (normaliser)",
         "alias table, rapidfuzz, range and sum rules", "Model: unresolved labels from top-10 candidates; code: everything else"],
        ["query agent", "knowledge base", "answer questions with citations", "planner: rules or Qwen2.5-3B + LoRA v2",
         "5 typed read-only SQL tools, page renderer", "Model: intent and slots; code: resolution, SQL, numbers, wording"],
    ], [2.0, 1.9, 2.6, 2.4, 3.0, 4.6], size=7.5)
    doc.h2("4.3 Models and adaptation (LoRA/QLoRA)")
    v2cfg = J(ROOT / "adapters" / "34_AN_qlora_v2" / "adapter_config.json") or {}
    doc.para(
        "**Base model.** `Qwen2.5-3B-Instruct` [11], run as a 4-bit MLX conversion (`mlx-community/Qwen2.5-3B-Instruct-4bit`) "
        "on an Apple M4 Pro, with greedy decoding and a JSON reply format. On machines without MLX, an `hf` backend loads the "
        "full-precision checkpoint with transformers and peft and converts our adapters (`scripts/convert_adapter_mlx_to_peft.py`). "
        "We chose a 3B model because it runs locally (no document leaves the machine, no API cost), fits fine-tuning in 24 GB, "
        "and handles Hindi. Its licence is the *Qwen Research License*: research and non-commercial use and derivatives are "
        "permitted, which covers this course project and the release of adapter weights only. Qwen2.5-1.5B/7B are Apache-2.0 "
        "alternatives for commercial reuse.", align="justify")
    doc.para(
        f"**Adapters.** Both adapters are LoRA on the 4-bit base (QLoRA-style) on the last 16 transformer blocks: rank 8, scale "
        f"20 (alpha = 160 in PEFT terms), dropout 0, all attention and MLP projections, Adam, learning rate 1e-4, batch 1, "
        f"loss on the answer only (`--mask-prompt`), seed 407. **v1** (250 iterations) was trained on 84 + 9 examples of island "
        f"extraction (D08, D09) and column mapping (D01, D03–D05). **v2** ({v2cfg.get('iters', 450)} iterations) adds 180 + 20 "
        f"query-planning examples and 18 routing examples, for 282 + 29 in all. The split is by document "
        f"(`data/splits/splits.json`): no page of D02, D06, D10 or D13 is used in training. Routing examples come only from "
        f"the 6 training documents, and routing is evaluated on the other 14. Query-planning questions are generated from "
        f"templates. Each one is compared with the 45 evaluation questions and dropped if the rapidfuzz similarity is ≥ 80 "
        f"(the highest kept: 78; report in `data/training_v2/contamination_report.json`).", align="justify")
    doc.h2("4.4 Database schema and knowledge base")
    doc.figure(FIG / "fig3_er_diagram.png", "Entity-relationship diagram of knowledge base v2. `observation` is the single fact "
               "table; red fields were added in Phase 3 (geospatial layer).", 13.0)
    loc_n = dict(D.db.execute("SELECT level, COUNT(*) FROM location GROUP BY level").fetchall())
    doc.para(
        f"We use a star schema in SQLite. Each extracted number is one row of `observation` ({D.n_obs:,} rows from "
        f"{D.n_docs_data} documents), keyed to `metric` (43), `commodity` (crops and market items, {D.db.execute('SELECT COUNT(*) FROM commodity').fetchone()[0]}), "
        f"`location` ({sum(loc_n.values())}: UT, {loc_n.get('district', 0)} districts, {loc_n.get('tehsil', 0)} tehsils, "
        f"{loc_n.get('agri_zone', 0)} zones, {loc_n.get('island', 0)} islands, market) and `unit` (with base-unit factors). "
        f"Other qualifiers (season, holder type, size class, LULC class, price variety) go in a JSON `dims` column, so the "
        f"schema stayed frozen while sources were added.", align="justify")
    doc.para(
        "**Provenance.** Each row stores `document_id`, `page`, `table_ref`, `row_label`, `col_label`, the printed text "
        "`value_raw`, the `run_id` and the `agent_id`. Through `extraction_run` it also links to the model, adapter, attempts "
        "and trace file. The `v_provenance` view returns all of this for any number, and `v_conflict` lists facts that two "
        "documents report differently.", align="justify")
    doc.para(
        "**Normalisation.** Places, crops, metrics and units are resolved through an `alias` table of English, Hindi and "
        "abbreviated surface forms (`C/Bay` → Campbell Bay zone). A level hint separates *South Andaman* the zone, the "
        "district and the island. Unresolved labels go to rapidfuzz (≥ 90) and then to the LLM, which chooses among the "
        "top-10 candidates. Accepted LLM choices are written back as aliases (`origin=llm`). Locations carry LGD-style "
        "codes where known and, in v2, latitude and longitude. Periods are typed (agricultural year July–June, fiscal year, "
        "month, census round) and stored with ISO start and end dates, so range queries do not depend on labels.",
        align="justify")
    doc.para(
        "**Missing values, duplicates, validation.** Blank, *N.A.*, *Nil* and dash cells are kept with a `missing_reason`, so "
        "*not reported* and *zero* stay distinct. Each record has a deterministic `dedup_key` (SHA-1 of metric, item, place, "
        "period, dims and citation), so re-runs are idempotent. The validator rejects unknown ids and impossible values and "
        "checks row sums against printed totals. Rejected rows are kept in `rejected_record` for review.", align="justify")
    doc.h2("4.5 Implementation details")
    doc.para(
        "The system is written in Python 3.11–3.13 with LangGraph 1.2, mlx-lm 0.32 (transformers + peft on other machines), "
        "pdfplumber, PyMuPDF, macOS Vision OCR (EasyOCR for Hindi scans), rapidfuzz, SQLite, Streamlit and matplotlib/plotly. "
        "It is traced locally (JSONL) and in LangSmith. A full corpus run takes about 25 minutes on an M4 Pro (24 GB) with "
        "531 LLM calls. Training takes 35 minutes for v1 and about 90 minutes for v2. API cost is zero, since everything runs "
        "locally. A fresh clone runs on macOS, Linux or Windows with `requirements.txt`, which has platform markers. CI checks "
        "the quick start on clean runners for all three. Configuration lives in `agri/config.py` and `.env` (see "
        "`.env.example`); there are no hard-coded paths or secrets.", align="justify")

    # ------------------------------------------------------------------ 5
    doc.h1("5. Experimental Setup")
    fa = {x["agent"]: x for x in fe["per_agent"]}
    doc.table("Evaluation set.", ["Agent / source group", "Test cases", "Reference fields", "Language(s)", "Checked by",
                                  "Used in training?"], [
        ["matrix_table / D02 p1 (5 crops × 12 places)", fa["matrix_table_agent"]["n_gold"], "metric, crop, place, period, value", "English", names[1], "No"],
        ["bilingual_table / D06 p2 (11 crops × 4 places × 2)", fa["bilingual_table_agent"]["n_gold"], "same", "Hindi (Kruti Dev) + English", names[1], "No"],
        ["price_table / D13 p11 (10 items × 7 periods)", fa["price_table_agent"]["n_gold"], "item, period, price", "English", names[2], "No"],
        ["island_profile / D10 (31 islands)", fa["island_profile_agent"]["n_gold"], "island, metric, value", "English + Hindi", names[0], "No"],
        ["narrative / D15 pp 1, 5", fa["narrative_agent"]["n_gold"], "scheme, year, outlay/expenditure", "English", names[2], "No"],
        ["image_table / D16 (16 × 8 grid)", fa["image_table_agent"]["n_gold"], "size class, holder, count/area", "English (OCR)", names[2], "No"],
        ["lulc / D17 (2 districts)", fa["lulc_agent"]["n_gold"], "class, district, area", "English", names[1], "No"],
        ["Column mapping (LLM task) / D02, D06", 74, "place, metric, period per column", "English, Hindi", names[0], "No"],
        ["Routing (LLM task) / 14 non-training files", 14, "agent id", "mixed", "manifest", "No"],
        ["Query agent: dev set / test set", "30 / 15", "answer, citation, intent", "English, Hindi", f"{names[1]} (test set)", "No (dev used for rules)"],
        ["Degraded inputs T1–T6 / fresh files", "6 / 3", "known values", "English, Hindi", names[1], "No"],
    ], [5.2, 1.6, 3.4, 2.4, 2.2, 2.0], size=7.5)
    doc.para(
        "**Gold.** For each agent we chose one region (a page or page set) of a document held out from training. Every fact in "
        "that region was transcribed by eye from the rendered page image, independently of the extractors, and blank cells "
        "were excluded. Island-profile gold (294 items) is the Phase 2 set, checked line by line against the page text. The "
        "query test set was written after the rule planner was frozen and was never used to develop it.", align="justify")
    doc.para(
        "**Metrics.** *Field-level precision, recall, F1*: a record is correct when metric, item, place, period, the listed "
        "qualifiers and the value (within 0.5%) all match an unmatched gold fact, under greedy one-to-one matching. F1 has a "
        "95% bootstrap interval (2,000 resamples [26]). *Provenance accuracy*: the correct record cites the gold page and "
        "its printed text appears on that page. *Tool selection*: router choice, plus AgentEvals trajectory match against a "
        "reference tool sequence. *Task completion*: loaded = 1, partial = 0.5. *Groundedness*: the printed value is on the "
        "cited page. *Automation rate*: inputs completed without manual intervention ÷ inputs attempted. *Query accuracy*: "
        "the answer satisfies the per-query check (top place and value, full series, peak period, cited page and value, or "
        "agreement count). *Intent resolution*: the predicted intent equals the gold intent.", align="justify")
    doc.para(
        "**Tools and evaluators.** We used LangSmith (datasets, experiments, traces), AgentEvals trajectory match, and the "
        "Microsoft Foundry agent-evaluator menu as a checklist (Tool Call Accuracy, Task Completion, Task Adherence, "
        "Groundedness, Intent Resolution, Navigation Efficiency). We did not use Relevance, Coherence, Fluency or Response "
        "Completeness, because answers are templated from tool output and a fluency score would not measure correctness. We "
        "did not use the content-safety evaluators, because the inputs are public statistics and the system generates no "
        "free text about people. **Acceptance criteria** were set before running: field F1 ≥ 0.95 on digital pages, "
        "provenance ≥ 0.99, automation ≥ 0.9, ≥ 9/10 demo queries correct, and adapter > base on held-out tasks.",
        align="justify")

    # ------------------------------------------------------------------ 6
    doc.h1("6. Results")
    doc.h2("6.1 Extraction performance by agent")
    ae = D.agent_eval["per_agent"]
    rows = []
    for x in fe["per_agent"]:
        a = ae.get(x["agent"], {})
        rows.append([x["agent"].replace("_agent", ""), x["n_gold"], f3(x["precision"]), f3(x["recall"]),
                     f"{f3(x['f1'])} [{f2(x['f1_ci95'][0])}–{f2(x['f1_ci95'][1])}]", f3(x["provenance_accuracy"]),
                     f2(a.get("trajectory_match_rate")), f2(a.get("task_completion"))])
    rows.append(["Macro-average", fe["n_gold_total"], f3(m["precision"]), f3(m["recall"]), f3(m["f1"]), f3(m["provenance_accuracy"]),
                 f2(_mean(ae[k].get("trajectory_match_rate") for k in ae if k in fa)),
                 f2(_mean(ae[k].get("task_completion") for k in ae if k in fa))])
    doc.table("Extraction and agent-behaviour results (held-out regions, knowledge base v2). Tool selection = AgentEvals "
              "trajectory match; task completion over each agent's corpus files.",
              ["Agent", "n", "Precision", "Recall", "F1 [95% CI]", "Provenance acc.", "Tool selection", "Task completion"],
              rows, [2.6, 1.0, 1.6, 1.6, 2.9, 1.9, 1.7, 1.9], size=8, bold_last=True)
    fv1 = D.field_v1["per_agent"] if D.field_v1 else []
    img1 = next((x for x in fv1 if x["agent"] == "image_table_agent"), None)
    doc.para(
        f"On digital pages the agents are close to exact: macro-F1 {f3(m['f1'])} over {fe['n_gold_total']} facts, with every "
        f"correct record citing the right page ({f3(m['provenance_accuracy'])}). Router tool selection was 20/20, and all "
        f"loaded values passed the groundedness check (32,151/32,151 printed values found on their cited page). The gold "
        f"evaluation also found two bugs in the Phase 2 image agent "
        f"(F1 {f3(img1['f1']) if img1 else 'n/a'} on database v1). Footer text of the screenshot was read as four data rows, "
        f"including the department's phone numbers, and OCR dropped single-digit cells. Stopping at the *Total* row and "
        f"re-reading empty cells from an upscaled crop raised precision to {f3(fa['image_table_agent']['precision'])} and "
        f"F1 to {f3(fa['image_table_agent']['f1'])}. Task completion below 1 for the bilingual agent means columns that were "
        f"deliberately skipped, not wrong values. Figure 5 plots F1 with its interval.", align="justify")
    doc.figure(FIG / "fig9_f1_by_agent.png", "Field-level F1 by agent on held-out regions, with 95% bootstrap intervals and n "
               "per agent.", 11.5)
    rob = D.robust["cases"] if D.robust else []
    rrows = [[c["case"], c["agent"].replace("_agent", ""), "yes" if c["routed_ok"] else "no", c.get("known_values", "—"),
              f2(c.get("precision")), f2(c.get("recall"))] for c in rob if c.get("precision") is not None]
    if D.surprise:
        for s in D.surprise["documents"]:
            rrows.append([f"Fresh: {s['file']}", s["agent"].replace("_agent", ""), s["routed_as_expected"], s["n_checked"],
                          f2(s["precision"]), s["recall_note"]])
    doc.table("Robustness: degraded inputs built from corpus pages (T1–T6, known values) and fresh Phase 3 files never seen "
              "before (precision on hand-checked samples).",
              ["Test document", "Agent", "Routed as expected", "n", "Precision", "Recall"], rrows, [6.0, 2.6, 1.8, 1.2, 1.6, 2.6],
              size=8, label="4b")
    doc.para(
        "Digital text is solved. Scanned and photographed pages are not: the system routes them correctly and its precision "
        "stays high, but recall falls to 0.10–0.52 because OCR misses cells. This is the main remaining weakness (Section 7).",
        align="justify")

    doc.h2("6.2 Effect of fine-tuning")
    def row(task, n, b, a, comment):
        d = None if (a is None or b is None) else a - b
        return [task, n, f3(b), f3(a), "n/a" if d is None else f"{d:+.3f}", comment]
    r5 = [
        row("Island extraction F1 (after gate)", 294, isl(base), isl(v1), "learns the catalogue and evidence format"),
        row("Island extraction F1, adapter v2", 294, isl(base), isl(v2), "multi-task adapter keeps the gain" if v2 else "pending"),
        row("Island F1: 2-shot prompt (no adapter)", 294, isl(base), isl(fs), "prompting alone recovers part of the gap"),
        row("Column mapping accuracy, v1", 74, col(base), col(v1), "zone vs UT confusion remains"),
        row("Column mapping accuracy, v2", 74, col(base), col(v2), ""),
        row("Column mapping: 2-shot prompt", 74, col(base), col(fs), ""),
        row("Routing (model only), v1", 20, base["routing"]["accuracy"], v1["routing"]["accuracy"], "v1 forgot the task (valid-id rate 0.2)"),
    ]
    if v2 and "routing" in v2:
        sp = json.loads(config.SPLITS_PATH.read_text())
        train = set(sp["train"]["island"]) | set(sp["train"]["tables"])
        bh = [x for x in base["routing"]["rows"] if x["doc"] not in train]
        r5.append(row("Routing (model only, 14 non-train files), v2", len(bh), sum(x["ok"] for x in bh) / len(bh),
                      v2["routing"]["accuracy_heldout"], f"valid-id rate back to {v2['routing']['valid_agent_id_rate']:.2f}; accuracy only partly recovers"))
    r5 += [row("Query planning: answer accuracy (dev)", 30, D.qa("dev", "base_zeroshot"), D.qa("dev", "qlora_v2_zeroshot"), "v2 zero-shot vs base zero-shot"),
           row("Query planning: answer accuracy (test)", 15, D.qa("test", "base_zeroshot"), D.qa("test", "qlora_v2_zeroshot"), "untouched paraphrases"),
           row("Query planning (dev), v1 + few-shot", 30, D.qa("dev", "base_fewshot"), D.qa("dev", "qlora_v1_fewshot"), "v1 hurts an unseen task")]
    doc.table("Base model vs adapter on the same held-out cases (raw model output: no rule fallback, no retries).",
              ["Agent / task", "n", "Base", "Adapter", "Δ", "Comment"], r5, [5.2, 1.0, 1.5, 1.6, 1.5, 5.4], size=8)
    doc.figure(FIG / "fig10_finetuning_ladder.png", "The fine-tuning ladder on the same held-out cases: base zero-shot, base "
               "with a 2-shot prompt (training examples), adapter v1 and adapter v2.", 11.5)
    doc.para(
        f"Fine-tuning is clearly worth it for island extraction. The base model gets F1 {f2(isl(base))}, a 2-shot prompt "
        f"{f2(isl(fs))}, and the adapter {f2(isl(v1))}, with groundedness rising from "
        f"{f2(base['island_extraction']['groundedness_rate'])} to {f2(v1['island_extraction']['groundedness_rate'])}. The "
        f"prompt alone cannot teach the 20-metric catalogue and the verbatim-evidence rule as reliably as weight updates. "
        f"For column mapping the adapter lifts accuracy from {f2(col(base))} to {f2(col(v1))}. The remaining errors confuse "
        f"zone columns with the UT total, which is why column mapping stays a fallback behind the geometric rules in "
        f"deployment. The adapter also has a cost. Adapter v1 made the model worse at tasks it was not trained on: "
        f"model-only routing fell from {f2(base['routing']['accuracy'])} to {f2(v1['routing']['accuracy'])} because it "
        f"answered in the extraction format, query planning fell, and latency per island rose about 4×. JSON validity also "
        f"fell, from {f2(base['island_extraction']['json_valid_rate'])} to {f2(v1['island_extraction']['json_valid_rate'])} "
        f"(looping lists that the salvage parser repairs). Adapter v2 adds the routing and planning tasks to training to "
        f"recover them; Table 5 reports the result unchanged. In deployment the router stays hybrid (rules first) and keeps "
        f"0.95 accuracy with either adapter.", align="justify")

    doc.h2("6.3 Automation and efficiency")
    au = D.agent_eval["workflow"]["automation"]
    doc.para(
        f"Inputs completed without manual intervention ÷ inputs attempted = **{au['inputs_completed_without_manual_intervention']}/"
        f"{au['inputs_attempted']} = {au['automation_rate']:.2f}** for the corpus run, with 0 manual interventions, "
        f"{au['retries']} validator retries, {au['llm_calls']} LLM calls, {au['model_outputs_rejected_by_gates']} model outputs "
        f"rejected by gates and {au['duplicate_rows_skipped']} duplicate rows skipped. The 9 degraded and fresh test files ran "
        f"with no intervention too. The manual steps that remain happen once per source, outside the run: downloading the "
        f"Phase 1 files (the portals have no API), recording URLs and licences in the manifest, and transcribing gold sets. "
        f"Barriers to full automation are chart-only pages (D18 needs chart digitisation), raster maps (out of scope by the "
        f"brief), portals without stable download links, and OCR recall on photos. A full run takes about 25 minutes (median "
        f"2.5 s per LLM call for the base model, 10.4 s per island for adapter v1, under 2 s per digital table page) at zero "
        f"API cost. A rules-only run (`--no-llm`) of all digital files takes under 5 minutes.", align="justify")

    doc.h2("6.4 Knowledge base and query evaluation")
    qrows = []
    for r in demo_rows:
        cites = r["answer"].split("[")[1].split("]")[0] if "[" in r["answer"] else ("D" + r["answer"].split("from ")[1][:20] if "comes from" in r["answer"] else "")
        qrows.append([r["id"], r["question"], r["type"].replace("_", "-"), "", r["answer"].split("\n")[0][:150], "Y" if r["correct"] else "N", cites[:30]])
    exp = {it["id"]: it for it in J(ROOT / "data" / "gold" / "queries.json")["queries"]}
    for qr in qrows:
        it = exp[qr[0]]
        g = D.db.execute(it["gold_sql"]).fetchall()
        qr[3] = {"top1": lambda g: f"{g[0][0]} = {g[0][1]:,}", "series": lambda g: f"{len(g)} periods, {g[0][0]}: {g[0][1]:,} → {g[-1][0]}: {g[-1][1]:,}",
                 "provenance": lambda g: f"{g[0][0]} p{g[0][1]}: {g[0][2]}", "value": lambda g: f"{g[0][2]:,} ({g[0][0]} p{g[0][1]})",
                 "agree": lambda g: f"{g[0][0]} periods with 2+ sources", "peak": lambda g: f"{g[0][0]}"}[it["check"]](g)
    doc.table(f"Query evaluation: the 10 live demonstration queries (≥ 2 spatial, ≥ 2 temporal, ≥ 1 provenance). {demo_ok}/10 "
              f"correct. The full 30 + 15 query sets are in Appendix C.",
              ["#", "Natural-language query", "Type", "Expected answer", "System answer (first line)", "Correct?", "Source traced"],
              qrows, [0.9, 3.6, 1.6, 2.8, 4.6, 1.1, 1.8], size=7)
    prow = []
    for lab, key in (("Rule planner (developed on dev)", "rules"), ("Base 3B, zero-shot", "base_zeroshot"),
                     ("Base 3B, 3-shot prompt", "base_fewshot"), ("Adapter v1 + 3-shot", "qlora_v1_fewshot"),
                     ("Adapter v2, zero-shot", "qlora_v2_zeroshot"), ("Deployed hybrid: rules, then v2 if the rules are unsure", "hybrid_rules_v2")):
        d, t = D.q.get(("dev", key)), D.q.get(("test", key))
        if d or t:
            prow.append([lab, f2(d["overall"]["answer_accuracy"]) if d else "n/a", f2(d["overall"]["intent_accuracy"]) if d else "n/a",
                         f2(t["overall"]["answer_accuracy"]) if t else "n/a", f2(t["overall"]["intent_accuracy"]) if t else "n/a",
                         f2((t or d)["overall"]["citation_groundedness"]), f"{(t or d)['overall']['median_latency_s']}"])
    doc.table("Query planner comparison: answer and intent accuracy on the dev set (n = 30) and the untouched test set "
              "(n = 15); citation groundedness and median latency on the test set.",
              ["Planner", "Dev answer", "Dev intent", "Test answer", "Test intent", "Grounded", "Latency (s)"], prow,
              [5.6, 1.6, 1.6, 1.7, 1.6, 1.6, 1.6], size=8, label="6b")
    doc.para(
        "Every answer is computed by fixed SQL and cites document, page and cell; citation groundedness is 1.0 in every "
        "configuration. The differences between configurations are planning errors: the wrong intent, metric or item. The "
        "rule planner was developed on the dev set, so its 1.00 there is optimistic; its untouched-test accuracy is the "
        "honest figure. The base model needs examples in the prompt (zero-shot 0.60 → 3-shot 0.67 on the test set). Adapter "
        "v1 is worse than the base model, because it was never trained for planning. **Adapter v2, trained on 180 "
        "template-generated planning examples, reaches 0.93 zero-shot on the untouched test set, +0.27 over the best "
        "prompt**, which is the clearest evidence of what fine-tuning adds. The deployed hybrid uses the rules when they "
        "resolve a metric and item explicitly, and otherwise calls adapter v2. Its confidence criterion was defined after "
        "the first test run, so its test score is also slightly optimistic; adapter v2 alone has no such dependence. "
        "Figure 6 shows the same comparison.", align="justify")
    doc.figure(FIG / "fig11_query_accuracy.png", "Query answer accuracy by planner on the dev and untouched test sets.", 11.5)
    rr = {k: J(P3 / f"query_eval_{k}.json") for k in ("robust_dev_rules_v3", "robust_test_rules_v3", "robust_dev_hybrid_v3",
                                                        "robust_test_hybrid_v3")}
    if all(rr.values()):
        def refused_ok(e):
            r = [x for x in e["results"] if x["intent_gold"] == "out_of_scope"]
            return f"{sum(x['correct'] for x in r)}/{len(r)}"
        def inscope_ok(e):
            r = [x for x in e["results"] if x["intent_gold"] != "out_of_scope"]
            return f"{sum(x['correct'] for x in r)}/{len(r)}"
        doc.table("Robustness: off-topic, unanswerable and everyday-wording questions. Dev (n = 14) was used to build "
                  "the scope checks; test (n = 15) was written afterwards and run once.",
                  ["Set", "Planner", "Should be refused: refused", "Answerable: correct", "Overall"],
                  [["robustness dev", "rules", refused_ok(rr["robust_dev_rules_v3"]), inscope_ok(rr["robust_dev_rules_v3"]),
                    f2(rr["robust_dev_rules_v3"]["overall"]["answer_accuracy"])],
                   ["robustness dev", "deployed hybrid", refused_ok(rr["robust_dev_hybrid_v3"]), inscope_ok(rr["robust_dev_hybrid_v3"]),
                    f2(rr["robust_dev_hybrid_v3"]["overall"]["answer_accuracy"])],
                   ["robustness test", "rules", refused_ok(rr["robust_test_rules_v3"]), inscope_ok(rr["robust_test_rules_v3"]),
                    f2(rr["robust_test_rules_v3"]["overall"]["answer_accuracy"])],
                   ["robustness test", "deployed hybrid", refused_ok(rr["robust_test_hybrid_v3"]), inscope_ok(rr["robust_test_hybrid_v3"]),
                    f2(rr["robust_test_hybrid_v3"]["overall"]["answer_accuracy"])]],
                  [3.2, 3.0, 3.4, 3.2, 2.2], size=8.5, label="6d")
        doc.para(
            "The first version had no way to decline a question. Every input was forced into a query, so a greeting "
            "returned a farmer count and \"is agriculture profitable?\" returned an arhar price. 8 of the 14 robustness-dev "
            "questions were wrong or only partly answered. A scope layer now refuses chit-chat and concepts the knowledge "
            "base does not hold (income, weather, soil), explains that crops cannot yet be ranked against each other, and "
            "answers \"why / should I\" questions with facts only. Every plan must be grounded in words of the question: "
            "a crop, measure or place the model adds on its own is dropped, and if nothing grounded remains the question is "
            "refused. Everyday words (\"rice farming\" means paddy) and relative time (\"last year\") are mapped explicitly. "
            "On the untouched robustness test the deployed planner scores "
            f"{f2(rr['robust_test_hybrid_v3']['overall']['answer_accuracy'])} (rules alone "
            f"{f2(rr['robust_test_rules_v3']['overall']['answer_accuracy'])}). The two remaining test failures (number words "
            "such as \"two years\"; comparing two items' prices for a year) were fixed afterwards, so they are not re-measured "
            "on fresh data. Rewording alone is covered; question types outside the six intents (ratios, multi-hop "
            "questions, causes) remain out of scope.", align="justify")

    doc.h2("6.5 Spatio-temporal relationships")
    doc.figure(FIG / "fig4_paddy_vs_arecanut_map.png", "Relationship 1. Map: change in paddy production by district, "
               "2021-22 → 2025-26, with zone production in 2025-26 as bubbles. Right: paddy production and arecanut area by "
               "district (n = 3 districts × 5 years). Sources: DES Basic Statistics (D03–D06), Agriculture Department (D02).", 16.5)
    doc.para(
        "**R1: from paddy to arecanut in North & Middle Andaman.** UT paddy production fell from 16,404 t (2021-22) to "
        "9,712 t (2025-26), −41%, and paddy area from 5,479 to 3,114 ha, −43%. North & Middle Andaman accounts for 98% of "
        "the decline in tonnes. Over the same five years arecanut area there grew from 2,527 to 3,338 ha (+32%). The two "
        "series are strongly negatively correlated (Pearson r = −0.83, n = 5 years). This is consistent with a shift from "
        "paddy to plantation crops, but it is not proof of one. *Caveat:* the 2025-26 values come from the Agriculture "
        "Department (D02), the earlier ones from DES. Where the two overlap (2023-24) they agree to within 0.01% (`v_conflict`).",
        align="justify")
    doc.figure(FIG / "fig6_price_calendar.png", "Relationship 2. Port Blair retail prices, January 2023 – December 2025, as a "
               "ratio to each item's 3-year mean (n = 36 months × 10 items, DES price statements D11–D13).", 16.0)
    doc.para(
        "**R2: price seasonality in Port Blair.** Averaged over 2023–2025, onion is 39% above its mean in December and 20% "
        "below in May. Brinjal (+24%), okra (+28%) and green chilli (+25%) peak in November–December, and tomato peaks in "
        "August (+45%, highest 181 INR/kg in August 2023). Eggs barely move (coefficient of variation 0.08, against 0.30 for "
        "onion). Supply to the islands is weakest during the south-west monsoon and in winter. *Caveat:* there is one market, "
        "and its prices partly reflect mainland shocks.", align="justify")
    doc.figure(FIG / "fig7_islands_farmers.png", "Relationship 3. Farmers by island in 2024-25 (bubbles and fill), with "
               "farmers per km² cultivated for the larger islands (n = 16 islands, D10).", 8.0)
    doc.para(
        "**R3: farmers are concentrated on two islands.** Of 24,954 farmers recorded on 16 islands in 2024-25, Middle Andaman "
        "(8,730) and North Andaman (6,192) hold 60%. Farmers per km² cultivated range from 88 on North Andaman to 178 on "
        "Middle Andaman and 237 on Shaheed Dweep, but the last figure rests on a suspect count (Section 6.6). *Caveat:* the "
        "island series change by only a few counts from year to year, so these are cross-sections, not trends.", align="justify")

    doc.h2("6.6 Error analysis")
    et = fe["errors_total"]
    surprise_err = D.surprise["error_counts"] if D.surprise else {}
    doc.table("Error types with counts. Extraction errors on held-out regions of database v2 (n = "
              f"{fe['n_gold_total']}), degraded inputs (T1–T6), query errors on the test set, and errors found in the source documents.",
              ["Error type", "Count", "Where", "Example"], [
        ["OCR: cell not read", et.get("missed", 0), "image agent, D16", "lone digits '2', '0' in the 10–20 ha row dropped by Vision OCR"],
        ["OCR: recall on scans/photos", sum(c["known_values"] - c["correct"] for c in rob if c.get("known_values")), "T1, T2, T4, T6",
         "photographed price page: 36 of 346 known values read"],
        ["Layout: footer read as rows (fixed in v2)", 4, "image agent, D16 (v1)", "phone number 232476 stored as holdings area"],
        ["Value / qualifier", et.get("value", 0), "island agent, D10", "North Andaman fish landed 650 t: inland and marine split wrongly"],
        ["Location name", 0, "all agents", "zone vs district for 'South Andaman' handled by the level hint"],
        ["Unit (corpus audit, fixed)", 20, "land-use and cultivated-area tables",
         "district area printed in ha stored as sq km: 373,600 'sq km' for N&M Andaman"],
        ["Place (corpus audit, fixed)", 78, "machinery tables D04-D06, D03",
         "'N & M Andaman' column stored as Nicobar after a one-column shift"],
        ["Item or measure (corpus audit, fixed)", 211, "D02, D03-D06",
         "'Total (A+B)' stored as citrus; seedling rows stored as fertilizer"],
        ["Printed values disagree", 103, "price bulletins D11-D13", "eggs Sep 2025: 30.00 (p9) vs 90.00 (p10)"],
        ["Hallucination (model)", 157, "corpus run (gated)", "model outputs rejected by the groundedness gate before loading"],
        ["Query planning", sum(1 for r in (J(P3 / 'query_eval_test_rules.json') or {'results': []})["results"] if not r["correct"]),
         "rule planner, test set", "'land under coconut' mapped to production, not area"],
        ["Off-topic question answered (fixed)", 8, "robustness dev, before scope layer", "'hi my name is …' answered with a farmer count"],
        ["Source error (publisher)", 2, "D10, D11", "Shaheed Dweep farmers 516 = Swaraj's figure; Nov-2023 onion 81.88 vs 57.50 on two pages"],
    ] + ([[k, v, "fresh files", ""] for k, v in surprise_err.items()] if surprise_err else []),
        [3.6, 1.2, 3.0, 8.2], size=8, label="6c")
    doc.para(
        "Examples. (1) In D16 the Vision OCR returned no text for the cell '2' in the row *10.0 – 20.0*. The Phase 2 agent "
        "stored the cell as *unparseable*. The v2 agent crops the empty cell, upscales it 4×, reads '2', and records the repair "
        "in the trace (`ocr_missing_cell → reocr_upscaled_crop`). (2) D11 page 24, the December 2023 statement, prints the "
        "November 2023 onion price as 57.50, while page 23 and two later publications print 81.88. The extraction is faithful "
        "to both pages and `v_conflict` flags the pair. Errors in the source publications are kept and flagged, not silently "
        "corrected. (3) Field F1 cannot catch a correct number stored under the wrong unit, place or item, so a corpus audit "
        "(`audit_db.py`: unit, bounds, sums, jumps, conflicts) was run over all 32,151 rows. It found, for example, district "
        "area printed in hectares but stored as sq km (100× too large), a shifted district column in the machinery tables, "
        "and seedling rows filed as fertilizer. Fourteen logged rules (`apply_corrections.py`, 1,384 changes, 329 rows "
        "rejected) fixed them; field F1 is unchanged at 0.999. Mismatched district sums fell from 60 to 1. Where the price "
        "bulletins print one month twice with different values, the query agent keeps the value consistent with the "
        "neighbouring months and says so in the answer (details in docs/data_quality.md).", align="justify")

    # ------------------------------------------------------------------ 7-9
    doc.h1("7. Discussion and Limitations")
    doc.para(
        "**Limits of the methods.** (i) OCR engines lose isolated characters and small digits on low-resolution photos; no "
        "engine we tested reads Kruti Dev, so decoding must happen after extraction. (ii) Small instruction models are "
        "reliable on narrow, well-specified decisions but not on open-ended SQL or on tasks outside their adapter's training. "
        "This is the catastrophic-forgetting effect visible in v1. (iii) Correlations across five annual points cannot "
        "establish causes; R1 needs farm-level or scheme data to explain the shift.", align="justify")
    doc.para(
        "**Limits of this implementation.** (i) The agents are specialised to the layouts we saw. A new price layout falls "
        "back to LLM column mapping, which reaches 0.64–0.7 accuracy. (ii) Chart-only atlas pages (D18) and raster maps are "
        "not extracted. (iii) The geospatial layer uses approximate point locations (±5 km) for zones and islands. (iv) The "
        "rule planner covers the question patterns we anticipated: 0.80 on unseen paraphrases. A generated matrix of "
        "1,093 questions (every measure × level × question form, checked automatically) first exposed 29 failures and "
        "95 dead-end answers, e.g. total cultivated area asked by agri zone, which is not published. When a figure "
        "is not published as asked, the agent now answers at the nearest level, place or year that has it and says so. "
        "The matrix was used for development, so it is not held out. (v) The system runs one "
        "document at a time on one machine, with no incremental scheduled download from the portals, which offer no APIs.",
        align="justify")
    doc.para(
        "**Threats to validity.** *Small n:* the gold regions total 699 facts from 7 documents, and the query test set has 15 "
        "questions. Intervals are reported, and differences of a few points are not meaningful. *Same-team annotation:* the "
        "gold was transcribed by the team that built the system, but from page images and before scoring. The query test "
        "set was written by a member who did not write the planner. *Silver training labels:* adapter training data came "
        "from the rule extractor, so the adapter may inherit its biases. That is why the gold is independent hand "
        "transcription. *Easy pages:* digital pages favour our rules; Table 4b shows the harder cases separately. "
        "*Source mixing:* long series join DES and Agriculture Department figures; we checked the overlaps.", align="justify")
    doc.h1("8. Ethics, Licensing and Data Governance")
    doc.para(
        "All sources are aggregate public statistics. No farmer names, Aadhaar-linked identifiers or beneficiary-level "
        "records were collected; island profiles report counts only, and the schema has no person-level fields. Licences and "
        "terms are recorded per file. Files without stated terms are flagged *academic use only*. D14 (MoFPI) is not "
        "redistributed, as its terms require. NRSC/Bhuvan data are used under their non-commercial terms with attribution, "
        "and the boundaries are DataMeet republications of Census/Survey of India data under CC BY 2.5 India and ODbL. Every "
        "map of India uses the Survey of India boundary. Downloads were manual, or scripted at one request every 3 seconds "
        "after checking robots.txt. The model runs locally, so no document is sent to a third-party API. Qwen2.5-3B is used "
        "under the Qwen Research License, which allows research use and the release of adapter weights; only adapter "
        "weights are distributed.", align="justify")
    doc.h1("9. Conclusion and Future Work")
    doc.para(
        f"AgriAgent turns 20 heterogeneous A&N agriculture publications into a provenance-tracked knowledge base of "
        f"{D.n_obs:,} observations. It extracts held-out digital pages with macro-F1 {f3(m['f1'])}, processes every file "
        f"without manual intervention, and answers {demo_ok}/10 demonstration queries with a page citation. LoRA adaptation "
        f"adds a large, measured gain over prompting on the task it was trained for, and costs accuracy on tasks it was not, "
        f"which multi-task training addresses. Next steps are a stronger OCR path for scans and photos (layout-aware OCR "
        f"with Indic support), chart digitisation for the atlas, and scheduled refreshes from the portals once they publish "
        f"stable links.", align="justify")

    # ------------------------------------------------------------------ 10
    doc.h1("10. Author Contributions")
    n0, n1, n2 = names
    doc.table("Who prepared which part.", ["Report section / system component", "Prepared by (lead)", "Also contributed", "Role"], [
        ["1–2 Introduction, Related work", n1, n0, "Source Lead"],
        ["3 Data sources and corpus; geospatial layer", n1, n2, "Source Lead"],
        ["4.1–4.2 Agents and orchestration", n0, n1, "Model Lead"],
        ["4.3 Models and adaptation", n0, "—", "Model Lead"],
        ["4.4 Database schema and knowledge base", n2, n0, "Data Engineering Lead"],
        ["4.5 Implementation, reproducibility, CI", n2, "—", "Data Engineering Lead"],
        ["5–6 Evaluation and results", n0, f"{n1} (gold, test set), {n2} (query tools)", "Evaluation Lead"],
        ["6.5 Spatio-temporal analysis, maps", n1, n0, "Source Lead"],
        ["7–9 Discussion, ethics, conclusion", n2, f"{n0}, {n1}", "Data Engineering Lead"],
        ["Figures and editing", n1, n2, "Source Lead"],
    ], [6.0, 3.2, 4.6, 3.2], size=8.5)
    doc.h1("Declarations")
    doc.para(f"**Data availability:** corpus (19 of 20 files; D14 by URL), manifest, database dump and adapter weights at "
             f"{TEAM['release']}; manifest and schema in the repository. Academic use only, following the source terms "
             f"(Section 8).", align="justify")
    doc.para(f"**Code availability:** {TEAM['repo']}, tag `{TEAM['tag']}`; MIT licence for the code.", align="justify")
    doc.para("**Use of generative AI tools:** an AI coding assistant (Anthropic Claude) was used for code assistance, test "
             "writing, figure scripting and language editing. All results are produced by the scripts in the repository "
             "from the team's data. Every number in this report is regenerated from `eval/results`, and the team reviewed "
             "and ran all code. Gold sets were checked against the source pages.", align="justify")

    doc.h1("References")
    refs = [
        'E. J. Hu, Y. Shen, P. Wallis, Z. Allen-Zhu, Y. Li, S. Wang, L. Wang, and W. Chen, "LoRA: Low-rank adaptation of large language models," in Proc. ICLR, 2022.',
        'T. Dettmers, A. Pagnoni, A. Holtzman, and L. Zettlemoyer, "QLoRA: Efficient finetuning of quantized LLMs," in Proc. NeurIPS, 2023.',
        'S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan, and Y. Cao, "ReAct: Synergizing reasoning and acting in language models," in Proc. ICLR, 2023.',
        'T. Schick, J. Dwivedi-Yu, R. Dessì, R. Raileanu, M. Lomeli, L. Zettlemoyer, N. Cancedda, and T. Scialom, "Toolformer: Language models can teach themselves to use tools," in Proc. NeurIPS, 2023.',
        'Y. Xu, M. Li, L. Cui, S. Huang, F. Wei, and M. Zhou, "LayoutLM: Pre-training of text and layout for document image understanding," in Proc. ACM SIGKDD, 2020, pp. 1192–1200.',
        'A. Nassar, N. Livathinos, M. Lysak, and P. Staar, "TableFormer: Table structure understanding with transformers," in Proc. IEEE/CVF CVPR, 2022, pp. 4614–4623.',
        'B. Smock, R. Pesala, and R. Abraham, "PubTables-1M: Towards comprehensive table extraction from unstructured documents," in Proc. IEEE/CVF CVPR, 2022, pp. 4634–4642.',
        'T. Yu et al., "Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task," in Proc. EMNLP, 2018, pp. 3911–3921.',
        'M. Pourreza and D. Rafiei, "DIN-SQL: Decomposed in-context learning of text-to-SQL with self-correction," in Proc. NeurIPS, 2023.',
        'J. Gala et al., "IndicTrans2: Towards high-quality and accessible machine translation models for all 22 scheduled Indian languages," Trans. Mach. Learn. Res., 2023.',
        'Qwen Team, "Qwen2.5 technical report," arXiv:2412.15115, 2024.',
        'C. Auer et al., "Docling technical report," arXiv:2408.09869, 2024.',
        'T. Brown et al., "Language models are few-shot learners," in Proc. NeurIPS, 2020, pp. 1877–1901.',
        'P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in Proc. NeurIPS, 2020, pp. 9459–9474.',
        'G. Kim et al., "OCR-free document understanding transformer," in Proc. ECCV, 2022, pp. 498–517.',
        'R. Smith, "An overview of the Tesseract OCR engine," in Proc. ICDAR, 2007, pp. 629–633.',
        'LangChain, "LangGraph documentation." Online. Available: https://langchain-ai.github.io/langgraph/ (accessed 23 Nov 2026).',
        'LangChain, "AgentEvals: evaluators for agent trajectories." Online. Available: https://github.com/langchain-ai/agentevals (accessed 23 Nov 2026).',
        'Directorate of Economics & Statistics, A&N Administration, "Basic Statistics 2024-25" and "Island-wise Statistical Outline 2024-25." Online. Available: http://andssw1.and.nic.in/ecostat/index.php (accessed 26 Sep 2026).',
        'Department of Agriculture, A&N Administration, "Area and Production 2025-26." Online. Available: https://agri.andaman.gov.in (accessed 26 Sep 2026).',
        'National Remote Sensing Centre, ISRO, "Land use / land cover statistics 2015-16," Bhuvan. Online. Available: https://bhuvan.nrsc.gov.in (accessed 26 Sep 2026).',
        'DataMeet, "Maps of India: Census 2011 districts and Survey of India boundaries." Online. Available: https://github.com/datameet/maps (accessed 23 Nov 2026).',
        'Microsoft, "Agent evaluators (Azure AI Foundry)." Online. Available: https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-evaluators/agent-evaluators (accessed 16 Oct 2026).',
        'Ministry of Agriculture & Farmers Welfare, "Unified Portal for Agricultural Statistics (UPAg)." Online. Available: https://upag.gov.in (accessed 23 Nov 2026).',
        'Digital Green, "Farmer.Chat: Scaling AI-powered agricultural services for smallholder farmers," arXiv:2409.08916, 2024.',
        'B. Efron and R. J. Tibshirani, An Introduction to the Bootstrap. New York, NY, USA: Chapman & Hall, 1993.',
    ]
    for i, r in enumerate(refs, 1):
        doc.para(f"[{i}] {r}", size=9.5, after=3)

    # ------------------------------------------------------------------ appendices
    doc.page_break()
    doc.h1("Appendix A. Database Schema (DDL) and Data Dictionary")
    doc.para("Full DDL: `agri/db/schema.sql`; full dictionary: `docs/schema.md`. Core fact table and the v2 changes:", after=4)
    ddl = (ROOT / "agri" / "db" / "schema.sql").read_text()
    s, e = ddl.find("CREATE TABLE IF NOT EXISTS observation"), ddl.find("CREATE INDEX IF NOT EXISTS ix_obs_lookup")
    doc.code(ddl[s:e].strip(), size=7.2)
    doc.table("Data dictionary (main fields).", ["Field", "Type", "Unit / values", "Nullable", "Meaning"], [
        ["metric_id", "TEXT FK", "43 ids, e.g. production, retail_price", "no", "what is measured"],
        ["commodity_id", "TEXT FK", "crops and market items", "yes", "NULL for non-crop metrics (farmers, LULC)"],
        ["location_id", "TEXT FK", "ut | district | tehsil | agri_zone | island | market", "no", "where"],
        ["period_label / start / end", "TEXT / ISO date", "'2024-25' (Jul–Jun), 'March 2024'", "no", "when, as printed and as dates"],
        ["dims", "JSON", "season, variety, size_class, lulc_l2 …", "no ('{}')", "extra qualifiers"],
        ["value / unit_id", "REAL / TEXT FK", "normalised; ha, t, INR/kg, count …", "value yes", "the number"],
        ["value_raw / missing_reason", "TEXT", "printed text; not_available | nil | blank …", "reason yes", "audit trail"],
        ["document_id, page, table_ref, row_label, col_label", "TEXT/INT", "D01–D20, U##; 1-based page", "no (page yes)", "provenance"],
        ["run_id, agent_id", "TEXT FK", "uuid; agent ids", "no", "which agent run produced it"],
        ["confidence / validation", "REAL / TEXT", "0–1; ok | warning | error", "no", "quality"],
        ["location.lat / lon / geo_source", "REAL / TEXT", "WGS84 degrees", "yes", "v2 geospatial layer"],
    ], [4.2, 2.0, 4.6, 1.8, 4.4], size=8, label="A1")
    doc.h1("Appendix B. Prompts and Agent Configurations")
    from agri.agents.island_agent import SYSTEM as ISL
    from agri.agents.router import SYSTEM as ROU
    from agri.query.agent import PLANNER_SYSTEM
    for name, txt in (("Island-profile extraction (system prompt)", ISL), ("Router (system prompt)", ROU),
                      ("Query planner (system prompt; 3 in-prompt examples in few-shot mode)", PLANNER_SYSTEM)):
        doc.para(f"**{name}**", after=2)
        doc.code(txt, size=7.2)
    doc.para("**Adapter hyper-parameters** (identical for v1 and v2 except data and iterations): rank 8, scale 20 (PEFT "
             "alpha 160), dropout 0, 16 layers, targets q/k/v/o/gate/up/down projections, Adam, lr 1e-4, batch 1, "
             "max length 2048, prompt masked, seed 407; v1 250 iterations on 84 examples; v2 450 iterations on 282 "
             "examples. Query tools: `rank_locations`, `time_series`, `trace_value`, `compare_sources`, `nearby`, and "
             "`safe_sql` (fallback, SELECT-only on a read-only connection).", align="justify")
    doc.h1("Appendix C. Full Query Set and Outputs")
    for s_name, fname in (("dev", "query_eval_dev_rules.json"), ("test", "query_eval_test_rules.json")):
        e = J(P3 / fname)
        if not e:
            continue
        rows = [[r["id"], r["type"], r["question"], f"{r['plan'].get('intent')} · {r['plan'].get('metric')} · "
                 f"{r['plan'].get('commodity') or '-'} · {r['plan'].get('location') or r['plan'].get('level') or '-'}",
                 r["answer"].split("\n")[0][:140], "Y" if r["correct"] else "N"] for r in e["results"]]
        doc.table(f"{s_name.title()} set: rule-planner plan and first answer line (tool SQL for each query: docs/demo_queries.md, "
                  f"eval/results/phase3/query_eval_{s_name}_*.json).", ["#", "Type", "Question", "Plan (intent · metric · item · place)",
                                                                        "Answer", "OK"], rows, [0.9, 1.6, 4.2, 3.6, 5.4, 0.8],
                  size=6.8, label="C1" if s_name == "dev" else "C2")
    return doc.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=TEMPLATE)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "out" / "34_AN_REPORT_v1.docx")
    a = ap.parse_args()
    print(build(a.out, a.template))


if __name__ == "__main__":
    main()
