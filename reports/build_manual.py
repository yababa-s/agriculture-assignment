"""Build the user manual (34_AN_MANUAL_v1.docx, and the PDF with --pdf) from the course template.

  python reports/build_manual.py            # .docx only (contents page without page numbers)
  python reports/build_manual.py --pdf      # .docx + .pdf through Pages (macOS), contents page with page numbers

The manual follows the video walkthrough chapter by chapter: every command shown in the video appears here in the same
order, each followed by its real output. Outputs are captured from a fresh clone (reports/captured/*.txt).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

from agri import config  # noqa: E402
from reports.docx_kit import Doc  # noqa: E402

TEAM = json.loads((ROOT / "reports" / "team.json").read_text(encoding="utf-8"))
CAP = ROOT / "reports" / "captured"
TEMPLATE = Path.home() / "Desktop" / "Phase 3 requirements" / "TEAMID_STATE_MANUAL_template.docx"
OUT = ROOT / "reports" / "out" / "34_AN_MANUAL_v1.docx"
PY = ".venv/bin/python"

# colours: command, output, video marker, note
CMD_FILL, CMD_EDGE = "F1F3F1", "3E7B3E"
OUT_FILL, OUT_EDGE = "FAFBF8", "B9C7B3"
VID_FILL, VID_EDGE = "E9EFF8", "3F6FB5"
NOTE_FILL, NOTE_EDGE = "FFF7E0", "D9A400"

M = {m["role"].split()[0]: m["name"] for m in TEAM["members"]}          # Model / Source / Data
SUYASH, SHIKHAR, ABHINEET = M["Model"], M["Source"], M["Data"]
CHAPTERS = [  # time, chapter, manual sections, what is shown, presenter (same as the video script)
    ("00:00", "1 · Introduction", "1", "Repository page, architecture figure, study-area map", SHIKHAR),
    ("00:55", "2 · Installation and configuration", "2–4", "git clone → venv → pip install → .env → fetch_artifacts "
     "(3 checksums) → pytest (50 passed) → status", ABHINEET),
    ("03:15", "3 · Processing a document", "5.1, 5.2, 5.4", "Unseen Hindi PDF routed by the model (U01, 144 values) → "
     "show_trace → eval_fields (macro-F1 0.999)", SUYASH),
    ("05:30", "4 · Querying the knowledge base", "5.3", "Spatial (model planner), temporal, Hindi and provenance "
     "questions; --show-source opens the page; web app Ask and Map tabs", SUYASH),
    ("07:50", "5 · Maintenance", "6", "add-source on a scanned PDF (D21, 1,197 values) → adapters → backup → restore → "
     "check-licenses → prune-logs → scheduled workflow on GitHub Actions", ABHINEET),
    ("10:00", "6 · Troubleshooting and FAQs", "7–8", "Missing database and its fix; corrupted download (checksum) "
     "and its fix; one FAQ", SHIKHAR),
    ("11:10", "7 · Wrap-up", "—", "README results table and the release page", "all three"),
]


# ---------------------------------------------------------------------------------------------------- helpers
def cap(name: str, max_lines: int | None = None, width: int | None = None) -> str:
    p = CAP / f"{name}.txt"
    if not p.exists():
        raise SystemExit(f"missing captured output {p}: run the command in a fresh clone and save its output there")
    lines = p.read_text(encoding="utf-8").rstrip("\n").splitlines()
    if width:
        lines = [x if len(x) <= width else x[: width - 1] + "…" for x in lines]
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines] + ["…"]
    return "\n".join(lines)


def run(doc: Doc, command: str, output: str | None = None, note: str | None = None):
    """A command box ($ …) and, when given, the real output below it."""
    doc.box("$ " + command, CMD_FILL, CMD_EDGE, mono=True, size=8.5, bold_first=True, after=3 if output is not None else 8)
    if output is not None:
        doc.box(output, OUT_FILL, OUT_EDGE, mono=True, size=7.5, after=4 if note else 8, title="Expected output")
    if note:
        doc.para(note, size=10, after=8, align="justify")


def step(doc: Doc, n: int | str, text: str):
    p = doc.para(f"**Step {n}.** {text}", after=3)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(6)


def video(doc: Doc, i: int):
    t, ch, sec, _, who = CHAPTERS[i]
    doc.box(f"**Video chapter {ch}** (starts at about {t}) · presented by {who}. The video runs the commands of this section "
            "in the same order.", VID_FILL, VID_EDGE, size=9.5)


def note(doc: Doc, text: str):
    doc.box(text, NOTE_FILL, NOTE_EDGE, size=9.5)


def task(doc: Doc, purpose: str, inputs: str, output: str):
    doc.table(None, ["Purpose", "Input", "Output"], [[purpose, inputs, output]], [5.3, 5.3, 5.3], size=9)


def contents(doc: Doc, entries: list[tuple[int, str]], pages: dict[str, int] | None):
    doc.h1("Contents", new_page=True)
    if not entries:
        return
    t = doc.d.add_table(rows=len(entries), cols=2)
    t.autofit = False
    for i, (level, text) in enumerate(entries):
        for j, (val, w) in enumerate(((("" if level == 1 else "    ") + text, 14.4),
                                      (str(pages.get(text, "")) if pages else "", 1.5))):
            cell = t.cell(i, j)
            cell.width = Cm(w)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if j else WD_ALIGN_PARAGRAPH.LEFT
            pf = p.paragraph_format
            pf.space_before = Pt(6 if level == 1 and i else 0)
            pf.space_after = Pt(1)
            r = p.add_run(val)
            r.font.name = "Calibri"
            r.font.size = Pt(11 if level == 1 else 10)
            r.bold = level == 1
            if level == 1:
                r.font.color.rgb = RGBColor.from_string("1F3A1F")
    doc.spacer(6)


class ManualDoc(Doc):
    """Records every H1/H2 so the contents page can list them."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.headings: list[tuple[int, str]] = []
        self.started = False

    def h1(self, text: str, new_page: bool = False):
        if self.started:
            self.headings.append((1, text))
        if new_page:
            # end the previous page with a break run in its last (tiny) paragraph: a break paragraph or a break inside
            # the heading leaves a blank page when the heading does not fit on a nearly full page, and Pages copies a
            # page-break-before property onto every paragraph that follows
            body = self.d.element.body
            last = [el for el in body if el.tag != qn("w:sectPr")][-1]
            if last.tag != qn("w:p"):
                self.spacer(1)
                last = [el for el in body if el.tag != qn("w:sectPr")][-1]
            r = OxmlElement("w:r")
            rpr = OxmlElement("w:rPr")
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), "2")                      # 1 pt, so the break line fits on a nearly full page
            rpr.append(sz)
            r.append(rpr)
            br = OxmlElement("w:br")
            br.set(qn("w:type"), "page")
            r.append(br)
            last.append(r)
        p = super().h1(text)
        return p

    def h2(self, text: str):
        if self.started:
            self.headings.append((2, text))
        return super().h2(text)


# ---------------------------------------------------------------------------------------------------- content
def build(out: Path, template: Path, pages: dict[str, int] | None = None, entries: list | None = None) -> tuple[Path, list]:
    doc = ManualDoc(template, {"[TEAMID]": TEAM["team_id"], "[State]": TEAM["state"]})

    # cover ------------------------------------------------------------------------------------------------
    doc.title("AgriAgent: User Manual")
    doc.para(f"Intelligent Agriculture Information System for {TEAM['state']}", size=14, align="center", after=2)
    doc.para("Setup · Daily use · Maintenance · Troubleshooting · FAQs", size=11, align="center", after=12)
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    doc.table(None, ["Item", "Detail"], [
        ["Team ID / State", f"{TEAM['team_id']} / {TEAM['state']}"],
        ["Software version documented", f"git tag {TEAM['tag']} (commit {commit or '…'}) · release phase3-v1 · schema v2"],
        ["Manual version and date", "v1.1, 24 November 2026"],
        ["Video walkthrough", "34_AN_MANUAL_VIDEO_v1.mp4 (1080p, 8–12 min), submitted in the submission zip file"],
        ["Repository", TEAM["repo"]],
        ["Support contact", f"{SUYASH}, {TEAM['contact']}"]], [4.6, 11.3])
    doc.h2("Document control and contributions")
    doc.table(None, ["Manual section / video segment", "Prepared by", "Tested by", "Role"], [
        ["1–2 Overview, quick start", SHIKHAR, ABHINEET, "Source Lead"],
        ["3–4 Requirements, installation, configuration", ABHINEET, SHIKHAR, "Data Engineering Lead"],
        ["5 Using the system", SUYASH, SHIKHAR, "Model + Evaluation Lead"],
        ["6 Maintenance (sources, models, database)", ABHINEET, SUYASH, "Data Engineering Lead / Model Lead"],
        ["7–8 Troubleshooting, FAQs", SHIKHAR, ABHINEET, "Source Lead"],
        ["10 Video: recording, narration, editing", SUYASH, "all members", "each member narrates own segment"]],
        [6.0, 3.3, 3.0, 3.6])
    doc.h2("How to read this manual")
    doc.box("$ a command: copy everything after the $ and paste it into a terminal", CMD_FILL, CMD_EDGE, mono=True,
            size=8.5, bold_first=True, after=3)
    doc.box("what the command prints (captured from a fresh clone; times, ids and dates will differ)", OUT_FILL, OUT_EDGE,
            mono=True, size=7.5, after=6, title="Expected output")
    doc.box("**Video chapter** boxes mark where each video chapter starts and who presents it.", VID_FILL, VID_EDGE, size=9.5,
            after=6)
    note(doc, "**Windows:** replace `.venv/bin/python` with `.venv\\Scripts\\python` in every command. Run all commands from "
              "the repository folder `agriculture-assignment`.")
    contents(doc, entries or [], pages)
    doc.started = True

    # 1 ----------------------------------------------------------------------------------------------------
    doc.h1("1. About the System", new_page=True)
    video(doc, 0)
    doc.para(
        "AgriAgent reads the agriculture publications of the Andaman & Nicobar Islands (ruled PDF tables, bilingual tables "
        "whose Hindi is in the legacy Kruti Dev font, scanned pages, monthly price statements, island profiles, budget "
        "memoranda, screenshots and land-use tables). A router agent sends each file to one of seven specialist extraction "
        "agents. Every number is validated and stored in a SQLite knowledge base together with the document, page, table "
        "cell and agent that produced it. A query agent then answers questions in English or Hindi, with a citation on "
        "every line, and can open the source page with the cell boxed.", align="justify")
    doc.para("**Who it is for:** agriculture department analysts, researchers and new team members who maintain it.",
             align="justify")
    doc.para("**What it does not do:** it does not read raster maps or charts, it does not download from the portals by "
             "itself (they have no APIs), and it holds no personal or beneficiary-level data.", align="justify")
    doc.figure(config.FIGURES_DIR / "fig2_architecture.png", "System overview: sources → router → specialist agents → "
               "normaliser and validator → knowledge base → query agent and app.", 15.9)
    doc.h2("1.1 Components at a glance")
    doc.table(None, ["Component", "What it does", "Location in repo"], [
        ["Orchestrator", "LangGraph state graph: route → extract → normalise → validate → retry or load", "agri/orchestrator/graph.py"],
        ["Router (supervisor)", "chooses an agent per file: manifest rule, fingerprint rules, or the LLM", "agri/agents/router.py"],
        ["Extraction agents (7)", "matrix, bilingual, price, island profile, narrative, image, land use", "agri/agents/*.py"],
        ["Tools", "PDF grid reader, Kruti Dev decoder, OCR, parsers", "agri/tools/"],
        ["LLM client", "Qwen2.5-3B-Instruct via MLX (Mac) or transformers + peft (any OS), with a LoRA adapter",
         "agri/llm/client.py, adapters/"],
        ["Knowledge base", "SQLite schema v2, loader, migration", "agri/db/, db/"],
        ["Query agent", "planner (rules or LLM) + read-only typed tools + source-page renderer", "agri/query/"],
        ["Command line", "agriagent status | run | add-source | backup | restore | check-licenses | prune-logs",
         "agri/cli.py, scripts/"],
        ["Web app", "Ask, Map, Explore and Evaluation tabs", "app/streamlit_app.py"],
        ["Evaluation", "field, query, LLM and agent evaluations and their results", "scripts/eval_*.py, eval/results/"],
    ], [3.6, 8.0, 4.3])
    doc.figure(config.FIGURES_DIR / "fig1_study_area.png", "What the knowledge base covers: 3 districts, 8 agriculture "
               "zones and 31 islands (32,151 values).", 8.0)

    # 2 ----------------------------------------------------------------------------------------------------
    doc.h1(new_page=True, text="2. Quick Start (≤ 10 minutes)")
    doc.para("The shortest path from a fresh clone to an answered question. It needs no API key, no GPU and no model; "
             "Section 4 explains each step and shows its output.", align="justify")
    quick = [
        ("Clone the repository at the submission tag.",
         f"git clone {TEAM['repo']}.git && cd agriculture-assignment && git checkout {TEAM['tag']}"),
        ("Create a virtual environment and install the requirements (about 1–3 minutes).",
         f"python3 -m venv .venv && {PY} -m pip install -r requirements.txt"),
        ("Create the settings file. Nothing in it is required.", "cp .env.example .env"),
        ("Download and verify the database, adapters and corpus (about 150 MB).", f"{PY} scripts/fetch_artifacts.py"),
        ("Check the installation. Expected: 50 passed.", f"{PY} -m pytest"),
        ("Ask a question. Expected: Diglipur (agri zone) is highest with 6,941 t … [D02 p1].",
         f'{PY} scripts/ask.py "Which agri zone produced the most paddy in 2025-26?"'),
        ("Open the web app, then go to http://localhost:8501 in a browser.",
         f"{PY} -m streamlit run app/streamlit_app.py"),
    ]
    for i, (what, c) in enumerate(quick, 1):
        step(doc, i, what)
        doc.box("$ " + c, CMD_FILL, CMD_EDGE, mono=True, size=8.5, bold_first=True, after=4)

    # 3 ----------------------------------------------------------------------------------------------------
    doc.h1("3. System Requirements")
    doc.table(None, ["Requirement", "Minimum", "Recommended", "Notes"], [
        ["Operating system", "macOS 13, Ubuntu 22.04 or Windows 10/11", "macOS 14+ on Apple Silicon",
         "the LLM runs with MLX on Apple Silicon; elsewhere set LLM_BACKEND=hf (or none for rules only)"],
        ["Python", "3.11", "3.12 or 3.13", "tested on 3.12 (CI) and 3.13 (development)"],
        ["GPU", "none (rules-only path)", "Apple M-series 16 GB+ or CUDA 8 GB+", "hf on CPU works, about 10 s per call"],
        ["RAM / disk", "8 GB / 2 GB", "16–24 GB / 10 GB",
         "corpus 66 MB, database 22 MB, adapters 100 MB, base model 2 GB (MLX) or 6 GB (hf)"],
        ["Internet", "first run only", "—", "GitHub release and Hugging Face downloads"],
        ["Accounts and keys", "none", "LangSmith (free), Hugging Face (only if rate-limited)",
         "smith.langchain.com → Settings → API keys"],
    ], [3.0, 3.8, 3.4, 5.7], size=8.5)

    # 4 ----------------------------------------------------------------------------------------------------
    doc.h1(new_page=True, text="4. Installation and Configuration")
    video(doc, 1)
    doc.para("Use an empty folder: the video and this section start from a fresh clone. Each step shows its expected "
             "output; optional steps are marked (Optional).", align="justify")
    doc.h2("4.1 Install")
    step(doc, 1, "Clone the repository and check out the submitted version (tag `phase3-submission`).")
    run(doc, f"git clone {TEAM['repo']}.git && cd agriculture-assignment && git checkout {TEAM['tag']}",
        "Cloning into 'agriculture-assignment'...\nNote: switching to 'phase3-submission'.")
    step(doc, 2, "Create a virtual environment and install the requirements. Apple-only packages (`mlx-lm`, `ocrmac`) "
                 "carry platform markers and are skipped on Linux and Windows; GitHub CI runs this install on all three.")
    run(doc, f"python3 -m venv .venv && {PY} -m pip install -r requirements.txt",
        "Successfully installed … langgraph-… mlx-lm-… pdfplumber-… pymupdf-… streamlit-… (about 1–3 minutes)")
    step(doc, "3 (Optional)", "LLM on Linux or Windows (transformers + peft, about 2 GB more):")
    run(doc, f"{PY} -m pip install -r requirements-hf.txt", "Successfully installed torch-… transformers-… peft-…")
    step(doc, "4 (Optional)", "Hindi OCR for scanned pages on Linux or Windows (EasyOCR; macOS uses its built-in OCR):")
    run(doc, f"{PY} -m pip install -r requirements-ocr.txt", "Successfully installed easyocr-1.7.2 …")

    doc.h2("4.2 Configure")
    run(doc, "cp .env.example .env", "(no output)",
        "Nothing in `.env` is required: the backend is detected automatically. `.env` is git-ignored; never commit it and "
        "never show it in screenshots. A value set in the real environment takes priority over `.env`.")
    doc.table(None, ["Variable (.env)", "Purpose", "Example value", "Required?"], [
        ["LLM_BACKEND", "mlx (Apple Silicon) | hf (any OS) | none (rules only)", "mlx", "No (auto-detected)"],
        ["ADAPTER_PATH", "LoRA adapter used by the pipeline", "adapters/34_AN_qlora_v2", "No"],
        ["DB_PATH", "knowledge base file", "db/34_AN_knowledgebase_v2.sqlite", "No"],
        ["CORPUS_DIR", "folder with the raw documents", "data/raw", "No"],
        ["LANGSMITH_API_KEY", "send traces and evaluation runs to LangSmith", "lsv2_pt_…", "No (local traces always)"],
        ["LANGSMITH_PROJECT", "LangSmith project name", "34_AN_agriagent", "No"],
        ["HF_TOKEN", "Hugging Face downloads if rate-limited", "hf_…", "No"],
        ["TEAM_ID", "artifact names TEAMID_STATE_ARTIFACT_vN", "34", "No"],
    ], [3.5, 6.0, 4.3, 2.1], size=8.5)

    doc.h2("4.3 Obtain data, models and adapter weights")
    doc.para("The large files are attached to the GitHub release `phase3-v1`, not stored in git. The fetch script downloads "
             "each zip, checks its SHA-256 against `artifacts.json` and unpacks it: the database into `db/`, the two adapters "
             "into `adapters/`, the corpus into `data/raw/`. The 2 GB base model downloads from Hugging Face the first time "
             "the LLM is used.", align="justify")
    run(doc, f"{PY} scripts/fetch_artifacts.py", cap("fetch"),
        "**Offline:** download the three zips from the release page in a browser into a folder `release/` and add "
        "`--from-dir release/`. **D14** (MoFPI) is not redistributed; download it from the URL in "
        "`data/CORPUS_EXCLUDED.txt` (an archived copy is listed there too) into `data/raw/Miscellaneous/` and check its "
        "SHA-256.")

    doc.h2("4.4 Verify the installation")
    step(doc, 1, "Run the test suite (agents, validation, query tools, maintenance commands).")
    run(doc, f"{PY} -m pytest", cap("pytest"))
    step(doc, 2, "Check the installation status. Look for `\"observations\": 32151`, `\"schema_version\": \"v2\"` and the "
                 "backend.")
    run(doc, f"{PY} -m agri.cli status", cap("status"))

    # 5 ----------------------------------------------------------------------------------------------------
    doc.h1(new_page=True, text="5. Using the System (Help)")
    video(doc, 2)
    doc.h2("5.1 Process a new document")
    task(doc, "Extract a file the system has never seen (for example one handed over at a review).",
         "A PDF or image anywhere on disk.",
         "A batch summary, the values in the knowledge base as document U##, and a trace of every decision.")
    step(doc, 1, "Run the pipeline on the file. The router fingerprints it; because nothing is decisive, the fine-tuned "
                 "model (base model + adapter v2) chooses the agent.")
    run(doc, f"{PY} scripts/run_pipeline.py --adapter adapters/34_AN_qlora_v2 --files "
             "data/test_unseen/hindi_area_production_2025-26.pdf", cap("run_unseen"),
        "**Read it as:** document U01 was routed by the **model** to the matrix-table agent; 144 values were extracted, "
        "144 loaded, 0 rejected, with 1 LLM call. Values from an unseen layout are marked *unverified* until checked.")
    step(doc, 2, "Look at the trace: every decision and tool call, and who made it (by=model, by=rule, by=tool).")
    run(doc, f"{PY} scripts/show_trace.py U01 --records 3", cap("trace", width=88),
        "Line [5] is the routing decision **by=model** with the model's reason. Line [8] maps the Hindi column headings to "
        "agriculture zones; line [11] is the validator. The records at the end show the provenance, e.g. paddy production "
        "in Diglipur, 6,941.03 t, page 1, Hindi row label धान (paddy). Use `--no-llm` to process without a model.")

    doc.h2("5.2 Run the full pipeline for a source")
    task(doc, "Re-extract one document, a source group or the whole corpus after a fix.", "Document ids from "
         "data/manifest.csv.", "Fresh records; `--replace` deletes the document's old records first.")
    run(doc, f"{PY} scripts/run_pipeline.py --docs D02 --replace --no-llm", cap("run_d02"),
        f"Whole corpus with the adapter (about 25 min on an M-series Mac): `{PY} scripts/run_pipeline.py --fresh "
        "--adapter adapters/34_AN_qlora_v2`. Rebuild every artifact from scratch: `bash scripts/reproduce.sh`.")

    doc.h2("5.3 Query the knowledge base")
    video(doc, 3)
    task(doc, "Answer questions with citations.", "A question in English or Hindi.",
         "An answer in which every line ends with [document page]; optionally the plan, the SQL and the page image.")
    doc.para("The planner turns the question into intent, metric, crop, place and period: rules first, the fine-tuned "
             "model when the rules are unsure (or always with `--planner model`). A fixed, read-only SQL tool computes "
             "the answer, so the model never writes SQL.", align="justify")
    step(doc, 1, "**Spatial**, planned by the fine-tuned model; `--explain` prints the plan and the SQL.")
    sp = cap("ask_spatial").splitlines()
    i = next(k for k, x in enumerate(sp) if x.startswith("SQL:"))
    run(doc, f'{PY} scripts/ask.py --planner model --explain "Which agri zone produced the most paddy in 2025-26?"',
        "\n".join(sp[: i + 2] + ["       … (the rest of the read-only SELECT)"]),
        "`planner=model` shows that the model wrote the plan (about 4 s); the rules planner answers in under 0.1 s.")
    step(doc, 2, "**Temporal.**")
    run(doc, f'{PY} scripts/ask.py "How did paddy production in the UT change from 2019-20 to 2025-26?"',
        cap("ask_temporal"), "Five documents are combined; each year cites its own page.")
    step(doc, 3, "**Hindi.** The question asks for arecanut production in South Andaman in 2024-25.")
    run(doc, f'{PY} scripts/ask.py "दक्षिण अण्डमान में सुपारी का उत्पादन 2024-25"', cap("ask_hindi"),
        "The column heading `nf{k.k v.Meku` is दक्षिण अण्डमान typed in the Kruti Dev font; the bilingual agent decodes it.")
    step(doc, 4, "**Provenance**, opening the source page with the cell boxed in red.")
    run(doc, f'{PY} scripts/ask.py --show-source "Which source and page did the 2025-26 coconut production figure '
             'for A&N come from?"', cap("ask_prov"))
    doc.figure(CAP / "provenance_crop.png", "The page opened by `--show-source` (top of D02 page 1): the cell 118.616 "
               "(A&N Islands, production) is boxed in red and the row label Coconut is highlighted.", 15.9)
    step(doc, 5, "**Web app.** The first load takes about 15 s. Ask tab: pick a demo question or type your own. Map tab: "
                 "district crop statistics and island indicators with a year slider. Explore tab: every record of a "
                 "document with its provenance. Stop the app with Ctrl+C.")
    run(doc, f"{PY} -m streamlit run app/streamlit_app.py", "  Local URL: http://localhost:8501")
    note(doc, f"Ten ready-made demonstration questions: `{PY} scripts/ask.py --demo` (expected answers in "
              "`docs/demo_queries.md`).")

    doc.h2("5.4 View traces and evaluation results")
    doc.para("Every pipeline run writes `logs/traces/<run_id>.jsonl` (shown with `scripts/show_trace.py`, Section 5.1) and "
             "`logs/batch_<id>.json`; every question is logged to `logs/queries/<date>.jsonl`. With `LANGSMITH_API_KEY` set, "
             "the same runs appear in the LangSmith project `34_AN_agriagent` (Projects → 34_AN_agriagent → open a run to "
             "see the graph nodes, tool calls and LLM calls).", align="justify")
    step(doc, 1, "Re-run the field evaluation: each agent's output against values transcribed by hand from the pages.")
    run(doc, f"{PY} scripts/eval_fields.py", cap("eval_fields", width=96),
        "**Read it as:** 7 agents, each on a different document; macro-average precision 1.0, recall 0.998, F1 0.999; "
        "provenance (right page and cell) 1.0 for every agent.")
    doc.para("Other evaluations (results in `eval/results/phase3/`):", after=3)
    doc.box(f"$ {PY} scripts/eval_queries.py --label rules --planner rules              # query set, dev split\n"
            f"$ {PY} scripts/eval_queries.py --set test --label rules --planner rules   # query set, test split\n"
            f"$ {PY} scripts/eval_llm_tasks.py --label qlora_v2 --adapter adapters/34_AN_qlora_v2\n"
            f"$ {PY} scripts/make_eval_figures.py", CMD_FILL, CMD_EDGE, mono=True, size=8.5)

    # 6 ----------------------------------------------------------------------------------------------------
    doc.h1(new_page=True, text="6. Maintenance")
    video(doc, 4)
    doc.para("How someone else keeps the system running: new sources, model updates, scheduled checks, backups, logs and "
             "licences.", align="justify")
    doc.h2("6.1 Adding a new source")
    step(doc, 1, "Check the licence on the portal. If no terms are stated, record `academic use only`. Add the publisher to "
                 "`agri/sources.py` if it is new.")
    step(doc, 2, "Register the file: it is copied into the corpus and a manifest row with its SHA-256 and date is added.")
    run(doc, f"{PY} -m agri.cli add-source data/test_unseen/scan_area_production_2025-26.pdf --source-id SRC_AGRI "
             "--group G1_MATRIX_TABLES --url https://agri.andaman.gov.in --license \"academic use only\"",
        cap("add_source"))
    step(doc, 3, "Run it. The source group decides the agent (`docs/source_agent_map.md`); a scanned PDF is first OCR'd "
                 "into a searchable PDF. A new layout needs a new agent in `agri/agents/` (subclass `BaseAgent`, register "
                 "it in `registry.py`).")
    run(doc, f"{PY} -m agri.cli run --docs D21 --no-llm", cap("run_d21"),
        "**partial** means some OCR'd headings could not be mapped by the rules alone: those cells are left out and "
        "listed for review rather than guessed.")
    step(doc, 4, f"Add test cases: transcribe one page into `data/gold/field_gold.json`, run `{PY} scripts/eval_fields.py` "
                 "and accept the source only if its F1 is at least 0.95. Then run the licence check (6.6) and commit the "
                 "manifest row.")

    doc.h2("6.2 Updating an agent, prompt or model")
    run(doc, "ls adapters", cap("ls_adapters"),
        "Prompts live with their agents (`SYSTEM` in `agri/agents/island_agent.py` and `router.py`, `PLANNER_SYSTEM` in "
        "`agri/query/agent.py`); thresholds are in `agri/config.py`. After any change run `pytest` and the evaluations "
        "(5.4) and compare with `eval/results/phase3/` before deploying. To retrain the adapter:")
    doc.box(f"$ {PY} scripts/build_datasets.py       # training data from TRAIN documents only\n"
            f"$ {PY} scripts/build_datasets_v2.py    # adds routing and query planning (contamination check)\n"
            "$ DATA=data/training_v2 ADAPTER=adapters/34_AN_qlora_v3 ITERS=450 ./scripts/train_lora.sh  # ~90 min, Apple Silicon\n"
            f"$ {PY} scripts/eval_llm_tasks.py --label qlora_v3 --adapter adapters/34_AN_qlora_v3\n"
            f"$ {PY} scripts/convert_adapter_mlx_to_peft.py adapters/34_AN_qlora_v3   # for LLM_BACKEND=hf",
            CMD_FILL, CMD_EDGE, mono=True, size=8.5)
    doc.para("**Deploy** a new adapter only if held-out island F1, column accuracy and routing accuracy are at least as good "
             "as the current one: set `ADAPTER_PATH`, run `python scripts/package_release.py`, upload the zip to a new "
             "release and update `artifacts.json`. To change the base model, set `BASE_MODEL` (MLX) and `HF_BASE_MODEL` "
             "(hf), retrain, and check its licence.", align="justify")

    doc.h2("6.3 Scheduled updates")
    doc.para("The portals have no API, so new files are added by hand (6.1). What is scheduled is the health check of every "
             "source URL (robots.txt-aware, one request every 2 s), the licence check, a rules-only re-extraction of the "
             "price tables into a scratch database, and the evaluation. On GitHub this is "
             "`.github/workflows/scheduled_update.yml`: every Monday at 03:30 UTC, or **Actions → scheduled-update → Run "
             "workflow**; results are uploaded as a workflow artifact. On a local machine, use cron:", align="justify")
    doc.box("# crontab -e   (every Monday 09:00)\n0 9 * * 1 cd /path/to/agriculture-assignment && .venv/bin/python "
            "scripts/check_sources.py >> logs/cron.log 2>&1 && .venv/bin/python -m agri.cli backup >> logs/cron.log 2>&1",
            CMD_FILL, CMD_EDGE, mono=True, size=8.5)
    doc.para("**Monitor:** the workflow run must be green; in `logs/source_health.json` anything other than status 200 means "
             "a portal moved, so update `document_url` in the manifest.", align="justify")

    doc.h2("6.4 Database backup, restore and migration")
    step(doc, 1, "Back up. SQLite's online backup is consistent even while the app is open; a SHA-256 file is written next "
                 "to it.")
    run(doc, f"{PY} -m agri.cli backup", cap("backup"))
    step(doc, 2, "Restore. The checksum and `PRAGMA integrity_check` are verified before the file is replaced. With more than "
                 "one backup, give the full file name instead of `*`.")
    run(doc, f"{PY} -m agri.cli restore backups/*.sqlite.gz", cap("restore"))
    doc.para("**Migration:** upgrade a v1 database to v2 with `python -m agri.db.migrate --db db/34_AN_knowledgebase_v1.sqlite` "
             "(adds the geo columns and fills them from `data/geo/locations.csv`).", align="justify")

    doc.h2("6.5 Logs and monitoring")
    doc.table(None, ["Location", "Content", "Retention"], [
        ["logs/batch_<id>.json", "per batch: agent, status, counts, LLM calls, errors handled", "keep (small)"],
        ["logs/traces/<run_id>.jsonl", "every node, tool call, decision (by=model/rule) and error of one run", "90 days"],
        ["logs/queries/<date>.jsonl", "every question: plan, tool, citations, latency, raw model output", "90 days"],
        ["logs/train_lora_*.log", "adapter training loss curves", "keep"],
        ["eval/results/**.json", "evaluation outputs used by the report", "keep (in git)"],
        ["LangSmith 34_AN_agriagent", "the same traces, browsable", "per LangSmith plan"],
    ], [4.6, 8.3, 3.0], size=8.5)
    run(doc, f"{PY} -m agri.cli prune-logs --days 90", cap("prune"),
        "Add `--dry-run` to list the files first. **Check after each batch:** status *failed* or *needs_review*, "
        "`rejected` > 0, and rows in the view `v_conflict` (two documents disagree).")

    doc.h2("6.6 Licensing and compliance checks")
    run(doc, f"{PY} -m agri.cli check-licenses", cap("licenses"))
    doc.para("**Before adding data:** confirm the terms and record them; never add names, Aadhaar-linked IDs or beneficiary "
             "lists (aggregate first); respect robots.txt and keep to one request every 2–3 s. **Before sharing outputs:** "
             "do not redistribute files marked *do not redistribute* (D14); cite DES, the Department of Agriculture and "
             "NRSC; use Survey of India boundaries for maps of India (`docs/geo.md`). The base model's licence (Qwen "
             "Research License) allows research use; distribute adapter weights only.", align="justify")

    # 7 ----------------------------------------------------------------------------------------------------
    doc.h1(new_page=True, text="7. Troubleshooting")
    video(doc, 5)
    doc.para("Two problems are worked through step by step (they are the ones shown in the video); the table that follows "
             "lists every real problem we met, with the exact error text.", align="justify")
    doc.h2("7.1 Worked example: the database is missing")
    step(doc, 1, "Symptom: a question fails immediately (here the database was moved away to reproduce it).")
    run(doc, f'{PY} scripts/ask.py "Which agri zone produced the most paddy in 2025-26?"', cap("missing_db"))
    step(doc, 2, "Fix: run the command named in the message, then ask again; the answer is back.")
    run(doc, f"{PY} scripts/fetch_artifacts.py --only database", cap("fetch_db"))
    doc.h2("7.2 Worked example: a corrupted download")
    step(doc, 1, "Symptom: the zip on disk does not match its published checksum, so it is not unpacked.")
    run(doc, f"{PY} scripts/fetch_artifacts.py --only database", cap("checksum"))
    step(doc, 2, "Fix: delete the zip named in the message and fetch again.")
    run(doc, f"rm .cache/release/34_AN_database_v2.zip && {PY} scripts/fetch_artifacts.py --only database",
        cap("refetch"))
    doc.h2("7.3 Problems and fixes")
    doc.table(None, ["Symptom / exact error message", "Likely cause", "Fix"], [
        ["FileNotFoundError: database not found: db/34_AN_knowledgebase_v2.sqlite. Run: python scripts/fetch_artifacts.py "
         "--only database", "the release files were not downloaded", "run the command in the message (7.1)"],
        ["ERROR: checksum mismatch for 34_AN_database_v2.zip … Fix: delete .cache/release/34_AN_database_v2.zip and run "
         "the command again.", "interrupted or corrupted download", "delete the zip and fetch again (7.2)"],
        ["urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get "
         "local issuer certificate>", "python.org Python on macOS has no CA bundle (EasyOCR model download)",
         "run '/Applications/Python 3.13/Install Certificates.command'; fetch_artifacts already uses certifi"],
        ["skip D14: file not found at data/raw/Miscellaneous/food processing for sustainable growth.pdf",
         "D14 is not redistributed (licence)", "download it from the URL in data/CORPUS_EXCLUDED.txt"],
        ["D14 download link returns HTTP 404 (checked 24 Nov 2026)", "the ministry moved or removed the file; "
         "government links break often", "use the archived copy in data/CORPUS_EXCLUDED.txt; its SHA-256 matches the "
         "manifest. The document and its data are kept"],
        ["ssl: certificate not trusted by this Python (site may be up; open it in a browser)", "check_sources.py "
         "could not verify the portal's certificate chain", "open the URL in a browser; if it is gone, use the archived "
         "copy the script prints"],
        ["skip /tmp/broken.pdf: cannot be read as a document (FileDataError: Failed to open file '/private/tmp/broken.pdf' "
         "as type pdf.)", "a damaged or non-PDF file passed with --files", "re-download the file; the other files in the "
         "batch are still processed"],
        ["llm_error: LLM_BACKEND=mlx needs Apple Silicon with mlx-lm installed. Use LLM_BACKEND=hf … or LLM_BACKEND=none",
         "LLM path on Linux, Windows or an Intel Mac", "pip install -r requirements-hf.txt and set LLM_BACKEND=hf, or "
         "use --no-llm"],
        ["llm_error: adapters/34_AN_qlora_v2/peft not found. Convert the MLX adapter first: python "
         "scripts/convert_adapter_mlx_to_peft.py …", "hf backend with an adapter only in MLX format",
         "run the conversion command in the message"],
        ["llm_error: unknown LLM_BACKEND='foo' (use mlx, hf or none)", "typo in .env", "set LLM_BACKEND to mlx, hf or none"],
        ["ValueError: unknown source_id SRC_X; add it to agri/sources.py first (SRC_DES, SRC_AGRI, SRC_NRSC, SRC_BHUVAN, "
         "SRC_MOFPI)", "new publisher not registered", "add it to SOURCES in agri/sources.py, then run add-source again"],
        ["Hindi labels print as '/kku Paddy', 'Ukkfj;y Coconut'", "Kruti Dev legacy font read as Latin text",
         "expected in raw text; the bilingual agent decodes it. For a new file set legacy_font_encoding=True in the manifest"],
        ["ValueError: only a single SELECT statement is allowed / OperationalError: attempt to write a readonly database",
         "the query tools open the database read-only by design", "write through the pipeline or the ops commands"],
        ["hf backend returns empty answers ('' and parsed=None)", "transformers ≥ 5 returns a dict from "
         "apply_chat_template (fixed)", "use tag phase3-submission; the client tokenises the prompt itself"],
        ["App map shows the islands as tiny specks or fills the whole globe", "GeoJSON ring orientation (fixed)",
         "use tag phase3-submission; the app re-orients the polygons"],
        ["Training very slow ('tok/s 19' in the log)", "another MLX job shares the GPU",
         "run one GPU job at a time; checkpoints are saved every 50 iterations"],
        ["DeprecationWarning: builtin type swigvarlink has no __module__ attribute", "PyMuPDF warning under Python 3.13",
         "harmless; ignore"],
    ], [7.0, 4.1, 4.8], size=8)

    # 8 ----------------------------------------------------------------------------------------------------
    doc.h1("8. Frequently Asked Questions")
    faqs = {
        "General": [
            ("Which places and years does the knowledge base cover?", "The UT, 3 districts, 9 tehsils, 8 agriculture zones "
             "and 31 islands. Crops: 2019-20 to 2025-26. Prices: monthly, January 2019 to December 2025, plus April 2011. "
             "Island profiles: 2022-23 to 2024-25. Census items: 2011 and 2015-16. Land use: 2015-16."),
            ("Do I need a GPU or an API key?", "No. The database, the rules planner, the app, the figures and rules-only "
             "extraction run on any laptop. The LLM runs locally on Apple Silicon (MLX), or with LLM_BACKEND=hf on CPU or "
             "CUDA."),
            ("Does any document leave my machine?", "No. The model runs locally. Only LangSmith tracing sends run data, "
             "and only if you set LANGSMITH_API_KEY."),
        ],
        "Data and sources": [
            ("How do I know which document a number came from?", "Every answer line ends with [document page]. "
             "`--show-source` opens the page with the cell boxed; in SQL: SELECT * FROM v_provenance WHERE obs_id = …"),
            ("Two documents give different numbers. Which is right?", "Both are stored. The view v_conflict lists the "
             "differences; the query agent prefers checked records, then the value printed on most pages, then the "
             "newest publication, and reports how many other documents give the same fact."),
            ("Why is a value marked ⚠ unverified?", "It comes from a document processed with --files (an unseen layout). "
             "Check it against the page; a checked document always wins over it."),
            ("Why is D14 missing from the corpus download?", "Its terms forbid redistribution. Download it from the URL in "
             "data/CORPUS_EXCLUDED.txt, or from the archived copy listed there if the ministry link is broken."),
            ("A source link no longer works. Do we drop the document?", "No. Government portals move files often. The "
             "original URL stays as provenance and the data stay in the knowledge base; scripts/check_sources.py reports "
             "the nearest Internet Archive copy, which is accepted only if its SHA-256 matches the manifest."),
            ("Can I add data from another state?", "Yes: add locations to agri/db/seed.py and sources to agri/sources.py, "
             "then follow 6.1. The schema is state-agnostic."),
        ],
        "Models and agents": [
            ("Which model is used, and what does the adapter change?", "Qwen2.5-3B-Instruct (4-bit) with a LoRA adapter "
             "(v2). The adapter lifts held-out island-extraction F1 from 0.27 to 0.94 (report, Section 6.2)."),
            ("Can I run the system without the LLM?", "Yes: add --no-llm. Digital tables, prices, land use and the image "
             "agent are rule-based; island profiles and narrative documents then fall back to deterministic extractors "
             "with lower recall on new layouts."),
            ("What does by=model or by=rule in a trace mean?", "Who made that decision: the LLM or fixed code. The report's "
             "Table 2 lists which decisions each agent hands to the model."),
        ],
        "Database and queries": [
            ("Can I write my own SQL?", "Yes: open db/34_AN_knowledgebase_v2.sqlite in any SQLite client; see "
             "docs/schema.md and docs/sample_queries.md (10 queries with expected results)."),
            ("Why did my question get the wrong metric?", "The rules planner did not recognise the wording (for example "
             "'land under'). Add --explain to see the plan, rephrase with 'area', 'production' or 'price', or use "
             "--planner model."),
        ],
        "Maintenance and licensing": [
            ("How often should I back up?", "Before every pipeline run that writes to the main database, and weekly (6.3)."),
            ("How do I check that the manifest is complete before sharing?", "`python -m agri.cli check-licenses` must end "
             "with OK (6.6)."),
        ],
    }
    for topic, qs in faqs.items():
        doc.h3(topic)
        for q, a in qs:
            p = doc.para(f"**Q: {q}**", after=1)
            p.paragraph_format.keep_with_next = True
            doc.para(f"A: {a}", after=7, align="justify")

    # 9 ----------------------------------------------------------------------------------------------------
    doc.h1(new_page=True, text="9. Glossary and Reference")
    doc.table(None, ["Term", "Meaning"], [
        ["Agent", "a component that turns one kind of document into records, using tools and, where needed, the LLM"],
        ["Router / supervisor", "the agent that decides which extraction agent handles a file"],
        ["Observation", "one number in the knowledge base, with its metric, item, place, period, unit and provenance"],
        ["Provenance", "document, page, table, row label, column label, printed text, agent and run of an observation"],
        ["Kruti Dev", "a legacy Hindi font that stores Devanagari as Latin characters; decoded by agri/tools/krutidev.py"],
        ["LoRA / adapter", "small trained weight updates on top of the frozen base model (only these are distributed)"],
        ["LGD code", "Local Government Directory code: the permanent identifier of an Indian administrative unit"],
        ["Agri zone", "one of the 8 Department of Agriculture zones (Diglipur … Campbell Bay)"],
        ["Gold set", "reference values transcribed by hand from the source pages, used only for evaluation"],
        ["Groundedness gate", "rejects a model output whose evidence text or value is not on the page"],
        ["U## / D##", "an unseen document processed with --files / a document in the manifest"],
    ], [3.4, 12.5], size=9)
    doc.h2("9.1 Command reference")
    doc.table(None, ["Command (prefix .venv/bin/python)", "What it does", "Section"], [
        ["-m agri.cli status", "installation, database and backend status", "4.4"],
        ["scripts/fetch_artifacts.py [--only database] [--from-dir release/]", "download and verify the artifacts", "4.3"],
        ["-m pytest", "run the 50 tests", "4.4"],
        ["scripts/run_pipeline.py --files X.pdf [--adapter DIR] [--no-llm]", "process an unseen document", "5.1"],
        ["scripts/run_pipeline.py --docs D02 [--replace] [--no-llm]", "re-extract manifest documents", "5.2"],
        ["scripts/show_trace.py U01 --records 5", "a document's trace and records", "5.1"],
        ['scripts/ask.py "…" [--explain] [--show-source] [--planner model|rules] [--demo]', "ask questions", "5.3"],
        ["-m streamlit run app/streamlit_app.py", "the web app", "5.3"],
        ["scripts/eval_fields.py | eval_queries.py | eval_llm_tasks.py", "evaluations", "5.4"],
        ["-m agri.cli add-source FILE --source-id … --group … --url … --license …", "register a new document", "6.1"],
        ["-m agri.cli run --docs D21 [--no-llm]", "run a registered document", "6.1"],
        ["-m agri.cli backup | restore FILE", "database backup and restore", "6.4"],
        ["-m agri.cli prune-logs --days 90 [--dry-run]", "delete old traces", "6.5"],
        ["-m agri.cli check-licenses", "licence and manifest completeness check", "6.6"],
        ["make setup | fetch | test | quickstart | demo | app | eval | reproduce", "shortcuts (macOS/Linux, no prefix)", "—"],
    ], [8.6, 5.9, 1.4], size=8.5)

    # 10 ---------------------------------------------------------------------------------------------------
    doc.h1("10. Video Walkthrough")
    doc.para("The video 34_AN_MANUAL_VIDEO_v1.mp4 (1080p, 8–12 minutes) is submitted in the submission zip file. It starts "
             "from a fresh clone in an empty folder and follows this manual: each chapter below runs the commands of the "
             "listed sections in the order printed here. Every member presents the chapter they prepared. Start times are "
             "approximate.", align="justify")
    doc.table("Video storyboard and chapter list.", ["Starts at (approx.)", "Chapter", "Manual section", "What is shown on screen",
                                                     "Presenter"],
              [[t, ch, sec, what, who] for t, ch, sec, what, who in CHAPTERS], [1.3, 3.6, 1.8, 6.6, 2.6], size=8.5,
              label="10")
    return doc.save(out), doc.headings


# ---------------------------------------------------------------------------------------------------- PDF + page numbers
def render_pdf(docx: Path) -> Path:
    subprocess.run(["bash", str(ROOT / "reports" / "render.sh"), str(docx), str(docx.parent / "_render"), "40"], check=True)
    pdf = docx.parent / "_render" / (docx.stem + ".pdf")
    final = docx.with_suffix(".pdf")
    import pymupdf
    with pymupdf.open(pdf) as d:            # Pages can leave an empty page where a page ends exactly at a break
        def ink(p):                         # drawings other than the white page background
            return [x for x in p.get_drawings() if not (x.get("fill") == (1.0, 1.0, 1.0) and x["rect"] == p.rect)]
        empty = [i for i, p in enumerate(d) if not ink(p) and not p.get_images()
                 and not [x for x in p.get_text().splitlines() if x.strip() and "User Manual" not in x]]
        if empty:
            d.delete_pages(empty)
            print(f"removed {len(empty)} empty page(s) left by the Pages export: {[i + 1 for i in empty]}")
        d.save(final, garbage=3, deflate=True)
    pdf.unlink()
    return final


def heading_pages(pdf: Path, entries: list[tuple[int, str]]) -> dict[str, int]:
    import pymupdf
    pages: dict[str, int] = {}
    with pymupdf.open(pdf) as d:
        texts = [[" ".join(x.split()) for x in p.get_text().splitlines()] for p in d]
    start = next(i for i, t in enumerate(texts) if "Contents" in t) + 1
    for _, h in entries:
        key = " ".join(h.split())
        for i in range(start, len(texts)):
            if key in texts[i]:
                pages[h] = i + 1
                start = i
                break
    return pages


def finish_pdf(pdf: Path, entries: list[tuple[int, str]], pages: dict[str, int]) -> None:
    """Page numbers in the footer (Pages does not print the template's PAGE field) and a bookmark per section."""
    import pymupdf
    with pymupdf.open(pdf) as d:
        n = len(d)
        for i, page in enumerate(d, 1):
            if i == 1:
                continue
            r = page.rect
            text = f"Page {i} of {n}"
            w = pymupdf.get_text_length(text, fontname="helv", fontsize=8)
            page.insert_text(((r.width - w) / 2, r.height - 28), text, fontname="helv", fontsize=8, color=(0.4, 0.4, 0.4))
        toc = [[1, "Cover", 1], [1, "Contents", 2]] + [[lvl, h, pages[h]] for lvl, h in entries if h in pages]
        d.set_toc(toc)
        d.saveIncr()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=TEMPLATE)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--pdf", action="store_true", help="also export the PDF with Pages (macOS) and number the contents")
    a = ap.parse_args()
    _, entries = build(a.out, a.template)                                     # pass 1: learn the headings
    out, _ = build(a.out, a.template, pages={h: 0 for _, h in entries} if a.pdf else None, entries=entries)
    if a.pdf:
        pages = heading_pages(render_pdf(out), entries)                       # pass 2: real page numbers
        missing = [h for _, h in entries if h not in pages]
        if missing:
            print("warning: page not found for", missing)
        out, _ = build(a.out, a.template, pages=pages, entries=entries)
        pdf = render_pdf(out)
        finish_pdf(pdf, entries, heading_pages(pdf, entries))
        print(pdf)
    print(out)


if __name__ == "__main__":
    main()
