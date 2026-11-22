"""Build the user manual (34_AN_MANUAL_v1.docx) from the course template.

  python reports/build_manual.py [--template PATH] [--out reports/out/34_AN_MANUAL_v1.docx]

Expected outputs are real outputs captured from the commands (reports/captured/*.txt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from agri import config  # noqa: E402
from reports.docx_kit import Doc  # noqa: E402

TEAM = json.loads((ROOT / "reports" / "team.json").read_text())
CAP = ROOT / "reports" / "captured"
TEMPLATE = Path.home() / "Desktop" / "Phase 3 requirements" / "TEAMID_STATE_MANUAL_template.docx"


def cap(name: str, n: int | None = None) -> str:
    p = CAP / f"{name}.txt"
    if not p.exists():
        return "(run the command to see the output)"
    t = p.read_text().replace(str(ROOT) + "/", "").strip("\n")
    lines = t.splitlines()
    return "\n".join(lines[:n] + (["…"] if n and len(lines) > n else [])) if n else t


def toc(doc: Doc):
    p = doc.d.add_paragraph()
    r = p.add_run()
    for kind, text in (("begin", None), (None, 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None), (None, None), ("end", None)):
        if kind:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r._r.append(fc)
        elif text:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = text
            r._r.append(it)
        else:
            t = OxmlElement("w:t")
            t.text = "Right-click and choose Update Field to show the table of contents."
            r._r.append(t)


def cmd(doc: Doc, command: str, output: str):
    doc.code("$ " + command, size=8.5)
    doc.para("Expected output:", size=9, after=1, italic=True)
    doc.code(output, size=7.8)


def build(out: Path, template: Path) -> Path:
    doc = Doc(template, {"[TEAMID]": TEAM["team_id"], "[State]": TEAM["state"], "[System name]": "AgriAgent"})
    names = [m["name"] for m in TEAM["members"]]
    n0, n1, n2 = names
    doc.title("AgriAgent: User Manual")
    doc.para(f"Intelligent Agriculture Information System for {TEAM['state']}", size=14, align="center", after=2)
    doc.para("Setup · Daily use · Maintenance · Troubleshooting · FAQs", size=11, align="center", after=10)
    doc.table(None, ["Item", "Detail"], [
        ["Team ID / State", f"{TEAM['team_id']} / {TEAM['state']}"],
        ["Software version documented", f"git tag {TEAM['tag']} (release phase3-v1, schema v2)"],
        ["Manual version and date", "v1.0, 24 November 2026"],
        ["Video walkthrough", f"{TEAM['video']} · 34_AN_MANUAL_VIDEO_v1.mp4 · duration about 11:00"],
        ["Repository", TEAM["repo"]],
        ["Support contact", f"{n0}, {TEAM['contact']}"]], [5.0, 11.0])
    doc.h1("Document control and contributions")
    doc.table(None, ["Manual section / video segment", "Prepared by", "Tested by", "Role"], [
        ["1–2 Overview, quick start", n1, n2, "Source Lead"],
        ["3–4 Requirements, installation, configuration", n2, n1, "Data Engineering Lead"],
        ["5 Using the system", n0, n1, "Model + Evaluation Lead"],
        ["6 Maintenance (sources, models, database)", n2, n0, "Model Lead / DE Lead"],
        ["7–8 Troubleshooting, FAQs", n1, n2, "Source Lead"],
        ["10 Video: recording, narration, editing", n0, "all members", "each member narrates own segment"]], [6.2, 3.2, 3.2, 3.4])
    doc.h1("Contents")
    toc(doc)
    doc.page_break()

    # 1 -------------------------------------------------------------------
    doc.h1("1. About the System")
    doc.para(
        "AgriAgent reads agriculture publications of the Andaman & Nicobar Islands (PDF tables, bilingual Hindi tables in the "
        "Kruti Dev font, price statements, island profiles, budget memoranda, screenshots, land-use tables) and stores every "
        "number in a SQLite knowledge base, together with the document, page, table cell and agent that produced it. You can "
        "then ask questions in English or Hindi, such as *which zone grew most paddy*, *how did onion prices change* or "
        "*which page did this number come from*. You get answers with citations, maps, and an image of the source page with "
        "the cell highlighted. It is meant for agriculture department analysts, researchers and new team members.",
        align="justify")
    doc.para("**What it does not do:** it does not read raster maps or charts, it does not download from the portals on its "
             "own (they have no APIs), and it does not hold personal or beneficiary-level data.", align="justify")
    doc.figure(config.FIGURES_DIR / "fig2_architecture.png", "System overview: sources → router → specialist agents → "
               "normaliser and validator → knowledge base → query agent and app.", 16)
    doc.h2("1.1 Components at a glance")
    doc.table(None, ["Component", "What it does", "Location in repo"], [
        ["Orchestrator", "LangGraph state graph: route → extract → normalise → validate → retry/load", "agri/orchestrator/graph.py"],
        ["Router (supervisor)", "chooses an agent per file (manifest rule, fingerprint, LLM)", "agri/agents/router.py"],
        ["Extraction agents (7)", "matrix, bilingual, price, island, narrative, image, LULC", "agri/agents/*.py"],
        ["Tools", "PDF grid reader, Kruti Dev decoder, OCR, parsers", "agri/tools/"],
        ["LLM client", "Qwen2.5-3B via MLX (Mac) or transformers+peft (any OS); adapters", "agri/llm/client.py, adapters/"],
        ["Database", "SQLite schema v2, loader, migration", "agri/db/, db/"],
        ["Query agent", "planner + read-only typed tools + source-page renderer", "agri/query/"],
        ["Command line", "agriagent status | ask | run | fetch | backup | …", "agri/cli.py, scripts/"],
        ["Web app", "Ask, Map, Explore, Evaluation tabs", "app/streamlit_app.py"],
        ["Evaluation", "field, query, LLM and agent evaluations; results", "scripts/eval_*.py, eval/results/"],
    ], [3.6, 8.0, 4.4])

    # 2 -------------------------------------------------------------------
    doc.h1("2. Quick Start (≤ 10 minutes)")
    doc.para("The shortest path from a fresh clone to an answered question. No API key, GPU or model is needed. Details are in "
             "Sections 3–5. On Windows, replace `.venv/bin/python` with `.venv\\Scripts\\python`.", align="justify")
    doc.bullets([
        f"Clone the repository: `git clone {TEAM['repo']}.git && cd agriculture-assignment && git checkout {TEAM['tag']}`",
        "Create the environment: `python3 -m venv .venv` then `.venv/bin/python -m pip install -r requirements.txt` (3–5 min).",
        "(Optional) Copy `.env.example` to `.env`. Every variable has a default; only LangSmith tracing needs a key.",
        "Download and verify the database, adapters and corpus: `.venv/bin/python scripts/fetch_artifacts.py` (150 MB).",
        "Check the installation: `.venv/bin/python -m pytest` → `50 passed`.",
        "Ask a question: `.venv/bin/python scripts/ask.py --no-llm \"Which agri zone produced the most paddy in 2025-26?\"`",
        "Expected result: Diglipur zone, 6,941 t, cited as [D02 p1] (full output in Section 5.3).",
        "Open the app: `.venv/bin/python -m streamlit run app/streamlit_app.py` and go to http://localhost:8501.",
    ], numbered=True)
    doc.figure(config.FIGURES_DIR / "fig1_study_area.png", "What the knowledge base covers: 3 districts, 8 agriculture zones, "
               "31 islands.", 8.5)

    # 3 -------------------------------------------------------------------
    doc.h1("3. System Requirements")
    doc.table(None, ["Requirement", "Minimum", "Recommended", "Notes"], [
        ["Operating system", "macOS 13, Ubuntu 22.04, or Windows 10/11", "macOS 14+ on Apple Silicon", "LLM via MLX only on Apple Silicon; elsewhere use LLM_BACKEND=hf or none"],
        ["Python", "3.11", "3.12 or 3.13", "tested on 3.12 (CI) and 3.13 (development)"],
        ["GPU (for the adapter)", "none (rules-only path, CPU hf backend)", "Apple M-series 16 GB+ or CUDA 8 GB+", "hf on CPU works but takes about 10 s per call"],
        ["RAM / disk", "8 GB / 2 GB", "16–24 GB / 10 GB", "corpus 66 MB, DB 22 MB, adapters 100 MB, base model 2 GB (MLX) or 6 GB (hf)"],
        ["Internet", "first run only", "—", "GitHub release and Hugging Face downloads"],
        ["Accounts and keys", "none", "LangSmith (free), Hugging Face (only if rate-limited)", "smith.langchain.com → Settings → API keys; huggingface.co → Settings → Access tokens"],
    ], [3.0, 3.8, 3.4, 5.8], size=8.5)

    # 4 -------------------------------------------------------------------
    doc.h1("4. Installation and Configuration")
    doc.h2("4.1 Install")
    doc.para("**Step 1. Clone and enter the repository.**", after=2)
    cmd(doc, f"git clone {TEAM['repo']}.git && cd agriculture-assignment && git checkout {TEAM['tag']}",
        "Cloning into 'agriculture-assignment'...\nNote: switching to 'phase3-submission'.")
    doc.para("**Step 2. Create a virtual environment and install the requirements.** Apple-only packages (`mlx-lm`, `ocrmac`) "
             "carry platform markers and are skipped elsewhere. `make setup` does the same thing.", after=2)
    cmd(doc, "python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt",
        "Successfully installed agentevals-… langgraph-… mlx-lm-… (macOS only) pdfplumber-… pymupdf-… streamlit-…")
    doc.para("**Step 3 (Optional). LLM on Linux/Windows** (transformers + peft, about 2 GB more):", after=2)
    cmd(doc, ".venv/bin/python -m pip install -r requirements-hf.txt", "Successfully installed torch-… transformers-… peft-…")
    doc.para("**Step 4 (Optional). Hindi OCR for scanned pages** (EasyOCR, pulls in PyTorch):", after=2)
    cmd(doc, ".venv/bin/python -m pip install -r requirements-ocr.txt", "Successfully installed easyocr-1.7.2 …")
    doc.h2("4.2 Configure")
    doc.para("Copy `.env.example` to `.env` (git-ignored). Nothing is required; a value set in the real environment takes "
             "priority over `.env`.", after=4)
    doc.table(None, ["Variable (.env)", "Purpose", "Example value", "Required?"], [
        ["LLM_BACKEND", "mlx (Apple Silicon) | hf (any OS) | none (rules only)", "mlx", "No (auto-detected)"],
        ["ADAPTER_PATH", "LoRA adapter used by the pipeline", "adapters/34_AN_qlora_v2", "No"],
        ["DB_PATH", "knowledge base file", "db/34_AN_knowledgebase_v2.sqlite", "No"],
        ["CORPUS_DIR", "folder with the raw documents", "data/raw", "No"],
        ["LANGSMITH_API_KEY", "tracing and evaluation runs in LangSmith", "lsv2_pt_…", "No (local JSONL traces always)"],
        ["LANGSMITH_PROJECT", "LangSmith project name", "34_AN_agriagent", "No"],
        ["HF_TOKEN", "Hugging Face downloads if rate-limited", "hf_…", "No"],
        ["TEAM_ID", "artifact names TEAMID_STATE_ARTIFACT_vN", "34", "No"],
    ], [3.4, 6.0, 4.4, 2.2], size=8.5)
    doc.h2("4.3 Obtain data, models and adapter weights")
    doc.para("Large files live on the GitHub release `phase3-v1`, not in git. The fetch script downloads each zip, checks its "
             "SHA-256 against `artifacts.json` and unpacks it: the database into `db/`, adapters into `adapters/`, the "
             "corpus into `data/raw/`. Without internet, download the zips in a browser into `release/` and add "
             "`--from-dir release/`. The base model (2 GB) downloads from Hugging Face the first time the LLM is used. "
             "D14 (MoFPI) is not redistributed; download it from its URL in `release/CORPUS_EXCLUDED.txt` into "
             "`data/raw/Miscellaneous/`.", align="justify")
    cmd(doc, ".venv/bin/python scripts/fetch_artifacts.py", "release phase3-v1  (https://github.com/yababa-s/agriculture-assignment/releases/download/phase3-v1)\n"
        "[ok] database  34_AN_database_v2.zip  sha256 verified  -> db/\n[ok] adapters  34_AN_qlora_adapters_v2.zip  sha256 verified  -> adapters/\n"
        "[ok] corpus    34_AN_corpus_v1.zip  sha256 verified  -> data/raw/\n" + cap("verify", 6) + "\ndone")
    doc.h2("4.4 Verify the installation")
    cmd(doc, ".venv/bin/python -m pytest", cap("pytest"))
    cmd(doc, ".venv/bin/python -m agri.cli status", cap("status"))

    # 5 -------------------------------------------------------------------
    doc.h1("5. Using the System (Help)")
    doc.h2("5.1 Process a new document")
    doc.para("**Purpose:** extract a file the system has never seen, for example a document handed to you at a review. "
             "**Input:** a PDF or image. **Steps:** run the pipeline with `--files`. The router fingerprints the file, picks an "
             "agent (rules first, the LLM only when the file is ambiguous), extracts, validates and loads it as document "
             "`U##`. **Output:** a batch summary, records in the database, and a trace per run.", align="justify")
    cmd(doc, ".venv/bin/python scripts/run_pipeline.py --files ~/Downloads/new_document.pdf --adapter adapters/34_AN_qlora_v2",
        "batch B2026…  1 documents  …s  model=mlx-community/Qwen2.5-3B-Instruct-4bit + LoRA(adapters/34_AN_qlora_v2)\n"
        "doc  agent                   route  status        try   extr   load   rej  llm\nU01  island_profile_agent    rule   loaded          1    …\n"
        "summary -> logs/batch_B2026….json")
    doc.para("Then look at what was stored: `python scripts/show_trace.py U01 --records 5` prints the routing decision, every "
             "tool call and five records with their citations. Use `--no-llm` to process without a model (rules only).",
             align="justify")
    doc.h2("5.2 Run the full pipeline for a source")
    doc.para("Re-extract one source group, or the whole corpus, after a fix. `--replace` deletes that document's old records "
             "first, so a re-run never leaves stale rows.", align="justify")
    cmd(doc, ".venv/bin/python scripts/run_pipeline.py --docs D02 --replace --no-llm", cap("run_d02"))
    doc.para("Whole corpus with the adapter (about 25 min on an M-series Mac): `python scripts/run_pipeline.py --fresh "
             "--adapter adapters/34_AN_qlora_v2`. Rebuild every artifact from scratch: `bash scripts/reproduce.sh`.",
             align="justify")
    doc.h2("5.3 Query the knowledge base")
    doc.para("**Purpose:** answer questions with citations. **Input:** a question in English or Hindi. The planner turns it into "
             "intent, metric, item, place and period: rules first, the LLM when the rules are unsure. A fixed, read-only SQL "
             "tool computes the answer. Every line ends with [document page]. Add `--explain` to see the plan and SQL, and "
             "`--show-source` to open the cited page with the cell boxed in red.", align="justify")
    doc.para("**Spatial:**", after=1)
    cmd(doc, '.venv/bin/python scripts/ask.py --no-llm "Which agri zone produced the most paddy in 2025-26?"', cap("ask_spatial"))
    doc.para("**Temporal:**", after=1)
    cmd(doc, '.venv/bin/python scripts/ask.py --no-llm "How did paddy production in the UT change from 2019-20 to 2025-26?"', cap("ask_temporal"))
    doc.para("**Provenance** (opens the page image):", after=1)
    cmd(doc, '.venv/bin/python scripts/ask.py --no-llm --show-source "Which source and page did the 2025-26 coconut production figure for A&N come from?"', cap("ask_prov"))
    doc.figure(ROOT / "outputs" / "provenance" / "obs_1663_D02_p1.png", "The page opened by --show-source: D02 page 1, with the cell "
               "118.616 boxed and the row label highlighted.", 13)
    doc.para("Ten ready-made demonstration queries: `python scripts/ask.py --demo` (expected answers in `docs/demo_queries.md`). "
             "The same questions work in the app's **Ask** tab, which also has a **Map** tab (district choropleths and island "
             "indicators with a year slider) and an **Explore** tab (every record of a document with its provenance).",
             align="justify")
    doc.h2("5.4 View traces and evaluation results")
    doc.para("Every pipeline run writes `logs/traces/<run_id>.jsonl` (each decision marked by=model or by=rule, each tool call "
             "with its arguments and result) and `logs/batch_<id>.json`. Questions are logged to `logs/queries/<date>.jsonl`. "
             "With `LANGSMITH_API_KEY` set, the same runs appear in the LangSmith project `34_AN_agriagent` (Projects → runs → "
             "open a run to see the graph nodes, tool calls and LLM calls). Re-run the evaluations:", align="justify")
    doc.code("$ .venv/bin/python scripts/eval_fields.py                         # per-agent P/R/F1 against hand-transcribed gold\n"
             "$ .venv/bin/python scripts/eval_queries.py --label rules --planner rules\n"
             "$ .venv/bin/python scripts/eval_queries.py --set test --label rules --planner rules\n"
             "$ .venv/bin/python scripts/eval_llm_tasks.py --label qlora_v2 --adapter adapters/34_AN_qlora_v2   # Mac / hf\n"
             "$ .venv/bin/python scripts/make_eval_figures.py")
    doc.para("Expected (field evaluation): a table of 7 agents ending in `macro-average … 1.0 0.998 0.999` and the path "
             "`eval/results/phase3/field_eval_v2.json`.", size=9.5)

    # 6 -------------------------------------------------------------------
    doc.h1("6. Maintenance")
    doc.h2("6.1 Adding a new source")
    doc.bullets([
        "Check the licence on the portal. If no terms are stated, record `No explicit licence. Flagged: academic use only.`",
        "Add the publisher to `agri/sources.py` if it is new (id, name, portal URL, licence).",
        "Register the file. It is copied into the corpus, and a manifest row with its SHA-256 and collection date is appended:",
    ], numbered=True)
    doc.code('$ .venv/bin/python -m agri.cli add-source ~/Downloads/Fooditems2026.pdf --source-id SRC_DES \\\n'
             '      --group G3_PRICE_TABLES --url "http://andssw1.and.nic.in/ecostat/…" \\\n'
             '      --license "No explicit licence. Flagged: academic use only." --period 2026')
    doc.code("added D21 (Fooditems2026.pdf, pdf_digital, 24 pages) to data/manifest.csv\n"
             "next: agriagent run --docs D21   then add test cases to data/gold/ and run agriagent eval fields", size=7.8)
    doc.bullets([
        "Map it to an agent: the source group decides the agent (`docs/source_agent_map.md`). For a new layout, write a new "
        "agent in `agri/agents/` (subclass `BaseAgent`, register it in `registry.py`) and add its group to the router.",
        "Run it: `python scripts/run_pipeline.py --docs D21`.",
        "Add test cases: transcribe one page into `data/gold/field_gold.json` (a new region), then run "
        "`python scripts/eval_fields.py`. Accept the source only if its F1 is ≥ 0.95.",
        "Run `python -m agri.cli check-licenses` and commit the manifest row with a descriptive message.",
    ], numbered=True)
    doc.h2("6.2 Updating an agent, prompt or model")
    doc.para("Prompts live with their agents (`SYSTEM` in `agri/agents/island_agent.py`, `router.py`, and `PLANNER_SYSTEM` in "
             "`agri/query/agent.py`); thresholds are in `agri/config.py`. After any change, run `pytest` and the evaluation, "
             "and compare against `eval/results/phase3/` before deploying. To retrain the adapter:", align="justify")
    doc.code("$ .venv/bin/python scripts/build_datasets.py            # v1 data from TRAIN documents only\n"
             "$ .venv/bin/python scripts/build_datasets_v2.py         # adds routing + query planning (contamination check)\n"
             "$ DATA=data/training_v2 ADAPTER=adapters/34_AN_qlora_v3 ITERS=450 ./scripts/train_lora.sh   # Apple Silicon, ~90 min\n"
             "$ .venv/bin/python scripts/eval_llm_tasks.py --label qlora_v3 --adapter adapters/34_AN_qlora_v3\n"
             "$ .venv/bin/python scripts/convert_adapter_mlx_to_peft.py adapters/34_AN_qlora_v3   # for LLM_BACKEND=hf")
    doc.para("Deploy only if held-out island F1, column accuracy and routing accuracy are at least as good as the current "
             "adapter. Then set `ADAPTER_PATH`, run `python scripts/package_release.py`, upload the zip to a new release "
             "and update `artifacts.json`. To change the base model, set `BASE_MODEL` (MLX) and `HF_BASE_MODEL` (hf), retrain, "
             "and check the licence.", align="justify")
    doc.h2("6.3 Scheduled updates")
    doc.para("The portals have no API, so new files are added by hand (6.1). What is scheduled is the health check of every "
             "source URL (robots.txt-aware, 1 request every 2 s), the licence check, a rules-only re-extraction of the price "
             "tables into a scratch database, and the evaluation. On GitHub this is `.github/workflows/scheduled_update.yml` "
             "(Mondays 03:30 UTC, or **Actions → scheduled-update → Run workflow**); results are uploaded as a workflow "
             "artifact. On a local machine, use cron:", align="justify")
    doc.code("# crontab -e   (every Monday 09:00)\n0 9 * * 1 cd /path/to/agriculture-assignment && .venv/bin/python scripts/check_sources.py "
             ">> logs/cron.log 2>&1 && .venv/bin/python -m agri.cli backup >> logs/cron.log 2>&1")
    doc.para("Monitor: open `logs/source_health.json`. Anything other than status 200 means a portal moved; update "
             "`document_url` in the manifest.", align="justify")
    doc.h2("6.4 Database backup, restore and migration")
    cmd(doc, ".venv/bin/python -m agri.cli backup", cap("backup"))
    cmd(doc, ".venv/bin/python -m agri.cli restore backups/34_AN_knowledgebase_v2_<stamp>.sqlite.gz",
        "restored db/34_AN_knowledgebase_v2.sqlite (previous file kept as *.before_restore)")
    doc.para("The backup uses SQLite's online backup API, so it is consistent even while the app is open. Restore checks the "
             "SHA-256 and runs `PRAGMA integrity_check` before replacing the file. **Migration:** upgrade a v1 database to v2 "
             "with `python -m agri.db.migrate --db db/34_AN_knowledgebase_v1.sqlite` (adds the geo columns and fills them from "
             "`data/geo/locations.csv`).", align="justify")
    doc.h2("6.5 Logs and monitoring")
    doc.table(None, ["Location", "Content", "Retention"], [
        ["logs/batch_<id>.json", "per-batch summary: agent, status, counts, LLM calls, errors handled", "keep (small)"],
        ["logs/traces/<run_id>.jsonl", "every node, tool call, decision (by=model/rule), error of one document run", "90 days"],
        ["logs/queries/<date>.jsonl", "every question: plan, tool, citations, latency, raw model output", "90 days"],
        ["logs/train_lora_*.log", "adapter training loss curves", "keep"],
        ["eval/results/**.json", "evaluation outputs used by the report", "keep (versioned in git)"],
        ["LangSmith 34_AN_agriagent", "the same traces, browsable", "per LangSmith plan"],
    ], [4.6, 8.4, 3.0], size=8.5)
    cmd(doc, ".venv/bin/python -m agri.cli prune-logs --days 90 --dry-run", cap("prune"))
    doc.para("Check after each batch: status *failed* or *needs_review* in the batch summary, `rejected` > 0, and rows in "
             "`v_conflict` (two documents disagree).", align="justify")
    doc.h2("6.6 Licensing and compliance checks")
    cmd(doc, ".venv/bin/python -m agri.cli check-licenses", cap("licenses"))
    doc.para("Before adding data: confirm the terms and record them; never add files with names, Aadhaar-linked IDs or "
             "beneficiary lists (aggregate first); respect robots.txt and keep to 1 request every 2–3 s. Before sharing outputs: "
             "do not redistribute files marked *do not redistribute* (D14); cite DES/Agri Dept/NRSC; use Survey of India "
             "boundaries for maps of India (`docs/geo.md`). The base model's licence (Qwen Research License) allows research "
             "use; distribute adapter weights only.", align="justify")

    # 7 -------------------------------------------------------------------
    doc.h1("7. Troubleshooting")
    doc.table(None, ["Symptom / error message", "Likely cause", "Fix"], [
        ["FileNotFoundError: database not found: db/34_AN_knowledgebase_v2.sqlite. Run: python scripts/fetch_artifacts.py --only database",
         "the release files were not downloaded", "run the command in the message"],
        ["ERROR: checksum mismatch for 34_AN_database_v2.zip  expected 8efd83b8…  got 9396400b…", "interrupted or corrupted download",
         "delete the zip under .cache/release/ (or release/) and fetch again"],
        ["skip D14: file not found at data/raw/Miscellaneous/food processing for sustainable growth.pdf (see release/CORPUS_EXCLUDED.txt)",
         "D14 is not redistributed (licence)", "download it from the URL in CORPUS_EXCLUDED.txt into data/raw/Miscellaneous/"],
        ["llm_error: LLM_BACKEND=mlx needs Apple Silicon with mlx-lm installed. Use LLM_BACKEND=hf … or LLM_BACKEND=none",
         "running the LLM path on Linux, Windows or an Intel Mac", "pip install -r requirements-hf.txt and set LLM_BACKEND=hf, or use --no-llm"],
        ["llm_error: adapters/34_AN_qlora_v2/peft not found. Convert the MLX adapter first: python scripts/convert_adapter_mlx_to_peft.py …",
         "hf backend with an adapter only in MLX format", "run the conversion command in the message"],
        ["llm_error: unknown LLM_BACKEND='foo' (use mlx, hf or none)", "typo in .env", "set LLM_BACKEND to mlx, hf or none"],
        ["urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate>",
         "python.org Python on macOS has no CA bundle (EasyOCR's first model download)",
         "run '/Applications/Python 3.13/Install Certificates.command' (certifi is in requirements-ocr.txt)"],
        ["Hindi labels print as '/kku Paddy', 'Ukkfj;y Coconut'", "text in the Kruti Dev legacy font read as Latin",
         "expected in raw text; the bilingual agent decodes it (agri/tools/krutidev.py). For a new file, check the manifest flag legacy_font_encoding=True"],
        ["ValueError: only a single SELECT statement is allowed  /  OperationalError: attempt to write a readonly database",
         "query tools open the database read-only by design", "write through the pipeline or ops commands, never through ask/safe_sql"],
        ["ValueError: unknown source_id SRC_X; add it to agri/sources.py first (SRC_DES, SRC_AGRI, SRC_NRSC, SRC_BHUVAN, SRC_MOFPI)",
         "new publisher not registered", "add it to SOURCES in agri/sources.py, then run add-source again"],
        ["hf backend returns empty answers ('' and parsed=None)", "transformers ≥ 5 returns a dict from apply_chat_template (fixed in v3.0)",
         "update to tag phase3-submission; the client now tokenises the rendered prompt itself"],
        ["App map shows the islands as tiny specks or fills the whole globe", "GeoJSON ring orientation differs from what plotly expects (fixed)",
         "update to phase3-submission; the app re-orients polygons on load"],
        ["Training very slow ('tok/s 19' in the log)", "another MLX job (evaluation, pipeline) shares the GPU",
         "run one GPU job at a time; checkpoints are saved every 50 iterations"],
        ["DeprecationWarning: builtin type swigvarlink has no __module__ attribute", "PyMuPDF warning under Python 3.13", "harmless; ignore"],
    ], [6.3, 4.2, 5.5], size=7.8)

    # 8 -------------------------------------------------------------------
    doc.h1("8. Frequently Asked Questions")
    faqs = {
        "General": [
            ("Which places and years does the knowledge base cover?", "The UT, 3 districts, 9 tehsils, 8 agriculture zones and 31 "
             "islands. Crops: agricultural years 2019-20 to 2025-26. Prices: monthly, January 2019 to December 2025, plus April "
             "2011. Island profiles: 2022-23 to 2024-25. Census items: 2011 and 2015-16. LULC: 2015-16."),
            ("Do I need a GPU or an API key?", "No. The database, queries (rule planner), app, figures and rules-only extraction "
             "run on any laptop. The LLM runs locally on Apple Silicon (MLX), or with LLM_BACKEND=hf on CPU or CUDA."),
            ("Does any document leave my machine?", "No. The model runs locally. Only LangSmith tracing sends run data, and only "
             "if you set LANGSMITH_API_KEY."),
        ],
        "Data and sources": [
            ("How do I know which document a number came from?", "Every answer ends with [document page]. `--show-source` opens "
             "the page with the cell boxed; SQL: SELECT * FROM v_provenance WHERE obs_id = …."),
            ("Two documents give different numbers. Which is right?", "Both are stored. `v_conflict` lists the differences; the "
             "query agent cites the newest publication and reports how many other documents give the same fact."),
            ("Why is D14 missing from the corpus download?", "Its terms forbid redistribution. Download it from the URL in "
             "release/CORPUS_EXCLUDED.txt."),
            ("Can I add data from another state?", "Yes: add locations to agri/db/seed.py, sources to agri/sources.py, then follow "
             "6.1. The schema is state-agnostic."),
        ],
        "Models and agents": [
            ("Which model is used, and what does the adapter change?", "Qwen2.5-3B-Instruct (4-bit) with a LoRA adapter (v2). The "
             "adapter lifts held-out island-extraction F1 from 0.27 to 0.94; see the report, Section 6.2."),
            ("Can I run the system without the LLM?", "Yes: `--no-llm` everywhere. Digital tables, prices, LULC and the image "
             "agent are rule-based; island profiles and narrative documents then fall back to deterministic extractors with "
             "lower recall on new layouts."),
            ("What does by=model vs by=rule in a trace mean?", "Who made that decision: the LLM or fixed code. The report's Table 2 "
             "lists which decisions each agent hands to the model."),
        ],
        "Database and queries": [
            ("Can I write my own SQL?", "Yes: open db/34_AN_knowledgebase_v2.sqlite in any SQLite client; see docs/schema.md and "
             "docs/sample_queries.md (10 queries with expected results)."),
            ("Why did my question get the wrong metric?", "The rule planner did not recognise the wording (for example 'land under'). "
             "Use --explain to see the plan, rephrase with 'area'/'production'/'price', or use the LLM planner (the default when "
             "a backend is available)."),
        ],
        "Maintenance and licensing": [
            ("How often should I back up?", "Before every pipeline run that writes to the main database, and weekly (6.3)."),
            ("How do I check that the manifest is complete before sharing?", "`python -m agri.cli check-licenses` must end with OK."),
        ],
    }
    for topic, qs in faqs.items():
        doc.h2(topic)
        for q, a in qs:
            doc.para(f"**Q: {q}**", after=1)
            doc.para(f"A: {a}", after=6, align="justify")

    # 9 -------------------------------------------------------------------
    doc.h1("9. Glossary and Reference")
    doc.table(None, ["Term", "Meaning"], [
        ["Agent", "a component that turns one kind of document into records using tools and, where needed, the LLM"],
        ["Router / supervisor", "the agent that decides which extraction agent handles a file"],
        ["Observation", "one number in the knowledge base, with its metric, item, place, period, unit and provenance"],
        ["Provenance", "document, page, table, row label, column label, printed text, agent and run of an observation"],
        ["Kruti Dev", "a legacy Hindi font that stores Devanagari as Latin characters; decoded by agri/tools/krutidev.py"],
        ["LoRA / adapter", "small trained weight updates on top of the frozen base model (only these are distributed)"],
        ["LGD code", "Local Government Directory code: the permanent identifier of an Indian administrative unit"],
        ["Agri zone", "one of the 8 Department of Agriculture zones (Diglipur … Campbell Bay)"],
        ["Gold set", "reference answers transcribed by hand from the source pages, used only for evaluation"],
        ["Groundedness gate", "rejects a model output whose evidence text or value is not on the page"],
    ], [3.4, 12.6], size=8.5)
    doc.h2("9.1 Command reference")
    doc.table(None, ["Command", "What it does"], [
        ["python -m agri.cli status", "installation, database and backend status"],
        ["python scripts/fetch_artifacts.py [--only database] [--from-dir release/]", "download and verify artifacts"],
        ["python scripts/ask.py \"…\" [--no-llm] [--explain] [--show-source] [--demo]", "ask questions"],
        ["python -m streamlit run app/streamlit_app.py", "web app"],
        ["python scripts/run_pipeline.py --docs D02 | --files X.pdf [--replace] [--no-llm] [--adapter DIR]", "extract documents"],
        ["python scripts/show_trace.py D07 --records 5", "inspect a document's trace and records"],
        ["python -m agri.cli add-source FILE --source-id … --group … --url … --license …", "register a new document"],
        ["python -m agri.cli backup | restore FILE | check-licenses | prune-logs --days 90", "maintenance"],
        ["python scripts/eval_fields.py | eval_queries.py | eval_llm_tasks.py | eval_agents.py", "evaluations"],
        ["python scripts/make_figures.py; scripts/make_eval_figures.py; scripts/make_diagrams.py", "figures and animations"],
        ["python scripts/build_geo.py --download; python -m agri.db.migrate", "rebuild the geo layer; migrate v1 → v2"],
        ["make setup | fetch | test | quickstart | demo | app | eval | reproduce", "shortcuts (macOS/Linux)"],
    ], [9.4, 6.6], size=8.2)

    # 10 ------------------------------------------------------------------
    doc.h1("10. Video Walkthrough")
    doc.para(f"File: 34_AN_MANUAL_VIDEO_v1.mp4 (1080p, about 11 minutes) · link: {TEAM['video']}. The video starts from a fresh "
             "clone on a clean user account and follows this manual section by section. The chapters below are also in the "
             "video description.", align="justify")
    doc.table("Video storyboard and chapter list.", ["Time", "Chapter (manual section)", "What is shown on screen", "Presenter"], [
        ["00:00", "Introduction (1)", "problem, architecture figure, what the KB covers (map)", n1],
        ["01:00", "Installation and configuration (2–4)", "git clone → venv → pip install → .env → fetch_artifacts → pytest (50 passed) → status", n2],
        ["04:00", "Processing a document (5.1–5.2)", "run_pipeline --files on a fresh DES PDF; batch table; show_trace; LangSmith run", n0],
        ["06:00", "Querying (5.3)", "spatial, temporal, Hindi and provenance questions; --show-source opens the page; app Map tab", n0],
        ["08:00", "Maintenance (6)", "add-source, backup and restore, check-licenses, scheduled workflow", n2],
        ["09:45", "Troubleshooting and FAQs (7–8)", "missing-database error and its fix; checksum error; one FAQ", n1],
        ["10:40", "Wrap-up", "where the results and the manual are", "all"],
    ], [1.4, 3.8, 7.8, 3.0], size=8.2, label="10")
    return doc.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=TEMPLATE)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "out" / "34_AN_MANUAL_v1.docx")
    a = ap.parse_args()
    print(build(a.out, a.template))


if __name__ == "__main__":
    main()
