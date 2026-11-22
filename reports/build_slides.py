"""Build the Phase 3 presentation (34_AN_PRESENTATION_v1.pptx) from the course template.

  python reports/build_slides.py [--template PATH] [--out reports/out/34_AN_PRESENTATION_v1.pptx]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pptx import Presentation  # noqa: E402

from agri import config  # noqa: E402
from reports.build_report import Data, f2, f3  # noqa: E402
from reports.pptx_kit import by_name, fill_table, fit_movie, fit_picture, presenter, remove, set_lines  # noqa: E402

FIG, ANIM, OUT = config.FIGURES_DIR, config.FIGURES_DIR / "anim", ROOT / "reports" / "out"
TEAM = json.loads((ROOT / "reports" / "team.json").read_text())
TEMPLATE = Path.home() / "Desktop" / "Phase 3 requirements" / "TEAMID_STATE_PRESENTATION_template_institute.pptx"
GEN = FIG / "slides"
HEADLINES = {3: 'Three questions: can agents extract, does LoRA help, can it answer live?', 4: 'No tool we tested decodes Kruti Dev or keeps cell-level provenance', 5: '20 files, 6 modalities, 3 districts, 31 islands, 2011 to 2026', 6: 'Seven agents, one per source group, each with its own tools', 7: 'A supervisor routes each file; validator feedback drives retries', 8: 'A local 3B model with LoRA decides meaning; code writes every number', 9: '32,151 numbers, each traceable to its page and cell', 10: '699 hand-transcribed facts and 45 queries, none used in training', 12: 'Fine-tuning beats prompting: island F1 0.59 → 0.94, queries 0.67 → 0.93', 13: '20 of 20 files processed with no manual step, at zero cost', 16: 'Most errors are OCR on scans; 2 errors are in the sources themselves', 17: 'All three questions answered: F1 0.999, +0.67 from LoRA, 10/10 live'}


def poster_frame(mp4: Path) -> Path:
    out = GEN / f"{mp4.stem}_poster.png"
    GEN.mkdir(parents=True, exist_ok=True)
    import imageio
    r = imageio.get_reader(str(mp4))
    last = None
    for f in r:
        last = f
    imageio.imwrite(out, last)
    return out


def short_answer(a) -> str:
    """One-line answer with its citation, from the agent's structured result."""
    r0 = a.rows[0] if a.rows else {}
    cite = f"[{r0.get('document_id')} p{r0.get('page')}]" if r0.get("document_id") else ""
    fmt = lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:g}"  # noqa: E731
    if a.tool == "rank_locations":
        return f"{r0['location'].replace(' (agri zone)', '')}: {fmt(r0['value'])} {cite}"
    if a.tool == "nearby":
        return f"{r0['location']}: {fmt(r0['value'])} ({r0['distance_km']} km) {cite}"
    if a.tool == "time_series":
        s_ = a.summary
        return f"{fmt(s_['first'][1])} → {fmt(s_['last'][1])} ({s_['change_pct']:+}%), peak {s_['peak'][0]}"
    if a.tool == "trace_value":
        return f"{fmt(r0['value'])} ← {r0['document_id']} p{r0['page']}, cell '{r0['value_raw']}'"
    if a.tool == "compare_sources":
        return f"{a.summary['periods_agreeing_within_1pct']}/{a.summary['periods_with_2plus_sources']} multi-source years agree"
    return a.text.split("\n")[0][:60]


def problem_panel() -> Path:
    """Slide 3 visual: what the raw sources look like (bilingual Kruti Dev page, raw text layer, screenshot)."""
    import pymupdf
    GEN.mkdir(parents=True, exist_ok=True)
    d = pymupdf.open(config.CORPUS_DIR / "Basic Statistics/Year 2024-25.pdf")
    page = d[1]
    clip = pymupdf.Rect(80, 80, 560, 330)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), clip=clip)
    p1 = GEN / "problem_page.png"
    pix.save(p1)
    raw = page.get_text("text", clip=clip).replace("\n", " ")[:260]
    fig = plt.figure(figsize=(6.6, 5.2))
    a = fig.add_axes([0.0, 0.42, 1.0, 0.58])
    a.imshow(plt.imread(p1))
    a.axis("off")
    a.set_title("What the PDF shows (DES Basic Statistics 2024-25, p. 2)", fontsize=10, loc="left")
    b = fig.add_axes([0.0, 0.0, 1.0, 0.38])
    b.axis("off")
    b.text(0, 0.95, "What a standard PDF extractor returns (Kruti Dev legacy font):", fontsize=9.5, fontweight="bold", va="top")
    import textwrap
    b.text(0, 0.78, "\n".join(textwrap.wrap(raw, 80)[:5]), fontsize=8.5, family="monospace", va="top", color="#B03A2E")
    from matplotlib import font_manager
    deva = next((f.fname for f in font_manager.fontManager.ttflist if "Devanagari" in f.name or "Kohinoor" in f.name), None)
    fp = font_manager.FontProperties(fname=deva) if deva else None
    b.text(0, 0.12, "After our decoder:  नारियल Coconut · सुपारी Arecanut · काजू Cashewnut", fontsize=9.5, va="top",
           color="#1F6F3F", fontproperties=fp)
    out = GEN / "problem_panel.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def recall_panel(D) -> Path:
    b = D.llm["base"]["island_extraction"]["per_metric_recall"]
    a = D.llm["qlora_v1"]["island_extraction"]["per_metric_recall"]
    keys = sorted(b, key=lambda k: a.get(k, 0) - b.get(k, 0), reverse=True)[:12]
    fig, ax = plt.subplots(figsize=(5.9, 5.2))
    y = range(len(keys))
    ax.barh([i + 0.2 for i in y], [b[k] for k in keys], 0.4, color="#BBBBBB", label="base")
    ax.barh([i - 0.2 for i in y], [a.get(k, 0) for k in keys], 0.4, color="#009E73", label="+ LoRA adapter")
    ax.set_yticks(list(y))
    ax.set_yticklabels([k.replace("_", " ") for k in keys], fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("recall per metric (held-out D10, 31 islands)")
    ax.legend(fontsize=8.5, loc="lower right")
    ax.set_title("Example: what the adapter learned", loc="left", fontsize=11, fontweight="bold")
    out = GEN / "recall_panel.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def build(out: Path, template: Path) -> Path:
    D = Data()
    fe, m = D.field, D.field["macro"]
    prs = Presentation(str(template))
    S = prs.slides
    n0, n1, n2 = [x["name"] for x in TEAM["members"]]
    P = {0: f"Presenter: {n1} · Source Lead", 1: f"Presenter: {n0} · Model Lead", 2: f"Presenter: {n2} · Data Engineering Lead",
         3: f"Presenter: {n0} · Evaluation Lead"}
    base, fs, v1, v2 = D.llm["base"], D.llm["base_fewshot2"], D.llm["qlora_v1"], D.llm["qlora_v2"]
    isl = lambda e: e["island_extraction"]["after_groundedness_gate"]["f1"] if e else None  # noqa: E731
    col = lambda e: e["column_mapping"]["column_accuracy"] if e else None  # noqa: E731
    demo = json.loads((config.RESULTS_DIR / "phase3" / ("query_eval_dev_hybrid_rules_v2.json" if (config.RESULTS_DIR / "phase3" / "query_eval_dev_hybrid_rules_v2.json").exists() else "query_eval_dev_rules.json")).read_text())
    demo_rows = [r for r in demo["results"] if r["demo"]]
    demo_ok = sum(r["correct"] for r in demo_rows)
    q_test = D.qa("test", "hybrid_rules_v2") or D.qa("test", "rules")
    notes = {}

    # 1 title
    s = S[0]
    set_lines(by_name(s, "Text 4"), ["From scattered PDFs to cited answers: an agentic agriculture knowledge base for A&N Islands"])
    set_lines(by_name(s, "Text 1"), [f"{n0} · {n1} · {n2}", f"Team {TEAM['team_id']} · State: Andaman & Nicobar Islands · CS F/U 407 Artificial Intelligence · 25 November 2026"])
    notes[1] = f"{n1}: introduce the team and the one-line message."
    # 2 outline
    s = S[1]
    fill_table(by_name(s, "Table 0"), [
        ["Motivation, sources and study area", "3–6", n1, "Source Lead", "Source discovery, manifest, Kruti Dev decoder, geo layer", "3"],
        ["Architecture, agents and models", "7–9", n0, "Model Lead", "Orchestrator, agents, LoRA adapters v1/v2", "3"],
        ["Database and knowledge base", "10", n2, "Data Engineering Lead", "Schema v2, normaliser, validator, provenance", "1.5"],
        ["Evaluation and fine-tuning", "11–13", n0, "Evaluation Lead", "Gold sets, field/LLM evaluation, LangSmith", "3"],
        ["Automation and live queries", "14–15", n2, "Data Engineering Lead", "Query tools, CLI/app, reproducibility", "3"],
        ["Insights, limitations, conclusion", "16–18", n1, "Source Lead", "Spatio-temporal analysis, maps", "2"]], size=11)
    presenter(s, P[0])
    notes[2] = "Hand-overs: Abhineet → Suyash at slide 7 → Shikhar at 10 → Suyash at 11 → Shikhar at 14 → Abhineet at 16. Total 15.5 min."
    # 3 motivation
    s = S[2]
    set_lines(by_name(s, "Text 0"), ["A&N farm data: 20 PDFs, 5 publishers, Hindi hidden in a legacy font"])
    remove(by_name(s, "Text 4"))
    fit_picture(s, by_name(s, "Visual placeholder"), problem_panel())
    set_lines(by_name(s, "Text 5"), [
        "**Who needs it:** agriculture and planning analysts, researchers, extension staff",
        "**Their questions:** which zone grows most paddy? how did prices move? where does this number come from?",
        "**What is hard:** 3 geographies (district, zone, island); ruled tables with rotated headers; Hindi in Kruti Dev; screenshots; prose memoranda",
        "**Why agents:** each format needs different tools; an LLM decides what headers mean, code keeps every number exact and cited"], size=15)
    presenter(s, P[0])
    # 4 objectives
    s = S[3]
    set_lines(by_name(s, "Text 5"), ["Can an agentic pipeline extract every number from A&N agriculture files with field F1 ≥ 0.95 and a page citation?"], size=14)
    set_lines(by_name(s, "Text 8"), ["Does LoRA adaptation of a local 3B model beat the base model and a few-shot prompt on held-out documents?"], size=14)
    set_lines(by_name(s, "Text 11"), ["Can the knowledge base answer spatial, temporal and provenance questions live, in English and Hindi?"], size=14)
    set_lines(by_name(s, "Text 12"), ["**Contributions:** [1] supervisor + 7 specialist agents over 20 files, 6 modalities  [2] measured LoRA gain "
                                     f"(island F1 {f2(isl(base))} → {f2(isl(v1))}) and a multi-task adapter that repairs forgetting  "
                                     f"[3] provenance KB of {D.n_obs:,} numbers + geo layer + query agent  [4] three spatio-temporal findings"], size=14)
    presenter(s, P[0])
    # 5 related work
    s = S[4]
    t = D.tools
    def score(tool, case):
        e = t.get(tool)
        if not e:
            return "—"
        c = next((v for k, v in e.items() if k.startswith(case) and isinstance(v, dict)), None)
        return f"{c['correct']}/{c['of']}" if c and "correct" in c else "n/a"
    fill_table(by_name(s, "Table 0"), [
        ["pdfplumber / PyMuPDF", "No (vector text only)", "No (Kruti Dev → gibberish)", "No", f"Yes: Kruti Dev {score('pdfplumber', 'C3')} and {score('pymupdf', 'C3')}"],
        ["Docling (layout + TableFormer)", "Partly", "No", "No", f"Yes: raster grid {score('docling', 'C1')}, Kruti Dev {score('docling', 'C3')}"],
        ["LLM agents (ReAct, LangGraph)", "via tools", "model-dependent", "only if designed in", "Yes: base 3B routing 0.40 alone"],
        ["Text-to-SQL (Spider, DIN-SQL)", "—", "—", "No", "Not used: free SQL fragile at 3B"],
        ["This work", "Yes (OCR + re-OCR)", "Yes (decoder + LLM)", "Yes: page + cell", f"F1 {f3(m['f1'])} (n={fe['n_gold_total']})"]], size=11)
    set_lines(by_name(s, "Text 3"), ["**Gap:** methods exist for table structure and for agents, but none decode legacy-font Hindi or keep cell-level "
                                    "provenance (implementation gap); OCR recall on photos remains a method limit."], size=14)
    presenter(s, P[0])
    # 6 study area
    s = S[5]
    remove(by_name(s, "Text 4"))
    box = by_name(s, "Visual placeholder")
    a3 = ANIM / "anim3_island_farmers.mp4"
    if a3.exists():
        fit_movie(s, box, a3, FIG / "fig1_study_area.png")
    else:
        fit_picture(s, box, FIG / "fig1_study_area.png")
    for nm, val in (("Text 6", "20"), ("Text 9", "6"), ("Text 12", "2"), ("Text 15", "3")):
        set_lines(by_name(s, nm), [val])
    set_lines(by_name(s, "Text 7"), ["files from 5 publishers"])
    set_lines(by_name(s, "Text 10"), ["modalities"])
    set_lines(by_name(s, "Text 13"), ["languages (EN, HI)"])
    set_lines(by_name(s, "Text 16"), ["districts · 8 zones · 31 islands"])
    set_lines(by_name(s, "Text 17"), ["Years: crops 2019-20 → 2025-26; prices monthly 2019 → 2025; census 2011, 2015-16",
                                       f"{D.pages} pages → {D.n_obs:,} observations with citations",
                                       "Licences: 15 files no stated terms (academic use only), NRSC/Bhuvan non-commercial, D14 not redistributed"], size=13)
    presenter(s, P[0])
    notes[6] = "Click the map to play: farmers by island 2022-23 → 2024-25. Survey of India boundary in the inset of Figure 1."
    # 7 source-agent mapping
    s = S[6]
    fill_table(by_name(s, "Table 0"), [
        ["Zone/district crop tables", "PDF / English", "matrix_table", "pdfplumber grid, rotated headers, LLM header fallback", "Done"],
        ["DES Basic Statistics", "PDF, Kruti Dev / Hindi+English", "bilingual_table", "Kruti Dev decoder, LLM column mapping", "Done"],
        ["Monthly price statements", "PDF / English", "price_table", "statement parser, year checks", "Done"],
        ["Island profiles", "PDF prose / EN+HI", "island_profile", "line selector, LLM + groundedness gate", "Done"],
        ["Scheme memoranda, MoFPI", "PDF narrative", "narrative", "segmenter, LLM facts", "Partial"],
        ["Census screenshot", "PNG", "image_table", "Vision OCR, grid, re-OCR", "Done"],
        ["LULC statistics / maps", "PDF tables, raster", "lulc / skip", "table parser; rasters out of scope", "Partial"]], size=11)
    presenter(s, P[1])
    # 8 architecture
    s = S[7]
    remove(by_name(s, "Text 4"))
    fit_picture(s, by_name(s, "Visual placeholder"), FIG / "fig2_architecture.png")
    set_lines(by_name(s, "Text 5"), [
        "**Pattern:** supervisor/router in a LangGraph state graph",
        "**Why:** each source group needs different tools; a 3B model cannot hold all of them in one prompt",
        "**Rejected:** one generalist agent; fixed sequential pipeline; per-page sub-agents (more calls, no gain)",
        "**Retries and failures:** validator feedback → re-run (≤ 2); model outputs failing the evidence gate are dropped",
        "**Completion:** loaded | partial | needs_review | failed | skipped, per file; one bad file never stops a batch"], size=12)
    presenter(s, P[1])
    # 9 models
    s = S[8]
    set_lines(by_name(s, "Text 3"), [
        "**Base model:** Qwen2.5-3B-Instruct, 4-bit MLX, local (Qwen Research License: research use, adapters only shared)",
        "**Adapter:** LoRA r = 8, scale 20, 16 layers, all projections, lr 1e-4; v1 250 it., v2 450 it.",
        "**Training data:** v1 84 examples (D08, D09 islands; D01, D03–D05 columns); v2 +180 query plans +18 routing; eval documents never used",
        "**Model vs code:** model = routing when ambiguous, header meaning, island facts, query intent; code = every number, unit, id, SQL",
        "**Alternatives:** 7B (no room to fine-tune in 24 GB), API models (documents would leave the machine)"], size=12)
    remove(by_name(s, "Text 5"))
    fit_picture(s, by_name(s, "Visual placeholder"), recall_panel(D))
    presenter(s, P[1])
    # 10 KB
    s = S[9]
    remove(by_name(s, "Text 4"))
    vps = [x for x in s.shapes if x.name == "Visual placeholder"]
    fit_picture(s, vps[0], FIG / "fig3_er_diagram.png")
    remove(by_name(s, "Text 6"))
    prov = ROOT / "outputs" / "provenance" / "obs_1663_D02_p1.png"
    if prov.exists():
        from PIL import Image
        im = Image.open(prov)
        w, h = im.size
        crop = GEN / "prov_crop.png"
        im.crop((int(w * 0.45), int(h * 0.55), w, int(h * 0.70))).save(crop)
        fit_picture(s, vps[1], crop)
    loc_n = D.db.execute("SELECT COUNT(*) FROM location").fetchone()[0]
    set_lines(by_name(s, "Text 7"), [
        f"**Records:** {D.n_obs:,} observations · 13 tables · 4 views (v_provenance, v_conflict …)",
        f"**Normalisation:** {loc_n} places (UT → district → tehsil, 8 zones, 31 islands, lat/lon), alias table EN+HI, typed periods, base units",
        "**Validation and duplicates:** id, range and row-sum checks; deterministic dedup key; missing ≠ zero",
        "Above: coconut 2025-26 = 118.616 → D02 p1, cell boxed by `--show-source`"], size=11)
    presenter(s, P[2])
    notes[10] = "One row → its document, page, table, row and column; open it live with ask.py --show-source."
    # 11 eval setup
    s = S[10]
    fa = {x["agent"]: x for x in fe["per_agent"]}
    fill_table(by_name(s, "Table 0"), [
        ["Matrix · Bilingual · Prices", f"{fa['matrix_table_agent']['n_gold']} · {fa['bilingual_table_agent']['n_gold']} · {fa['price_table_agent']['n_gold']}", "5 per fact", f"{n1}, {n2}"],
        ["Islands · Narrative · Image · LULC", f"{fa['island_profile_agent']['n_gold']} · {fa['narrative_agent']['n_gold']} · {fa['image_table_agent']['n_gold']} · {fa['lulc_agent']['n_gold']}", "3–5", f"{n0}, {n2}"],
        ["LLM tasks: islands / columns / routing", "31 / 11 tables / 14", "294 / 74 / 14", n0],
        ["Queries: dev / untouched test", "30 / 15", "answer + page", n1],
        ["Total", f"{fe['n_gold_total']} facts + 45 queries", "", ""]], size=11)
    set_lines(by_name(s, "Text 3"), [
        "**Metrics:** field P/R/F1 (95% bootstrap CI), provenance accuracy, tool selection (AgentEvals trajectory), task completion, groundedness, intent resolution, query accuracy, automation rate",
        "**Tools:** LangSmith (datasets, experiments, traces), AgentEvals, Foundry evaluator checklist",
        "**Skipped and why:** fluency/coherence (answers are templated), content safety (public statistics, no free text about people)",
        "**Gold:** transcribed by eye from page images of held-out documents; no gold page used in training"], size=12)
    presenter(s, P[3])
    # 12 results
    s = S[11]
    set_lines(by_name(s, "Text 0"), [f"Macro F1 {f3(m['f1'])} on {fe['n_gold_total']} held-out facts; every correct number cites its page"])
    remove(by_name(s, "Text 4"))
    fit_picture(s, by_name(s, "Visual placeholder"), FIG / "fig9_f1_by_agent.png")
    rob = {c["case"][:2]: c for c in D.robust["cases"]}
    set_lines(by_name(s, "Text 5"), [
        f"**Digital pages are solved:** 6 of 7 agents ≥ 0.99 F1; provenance accuracy {f3(m['provenance_accuracy'])}",
        f"**Gold eval found 2 bugs:** footer phone numbers read as data, OCR dropping lone digits → image agent F1 0.969 → {f3(fa['image_table_agent']['f1'])}",
        f"**Failure:** scans and photos: photo of a price table recall {f2(rob['T2']['recall'])}, scanned bilingual page {f2(rob['T4']['recall'])}: OCR, not routing",
        "**Fresh files:** known layout 15/15 correct; new 'at a glance' layouts 5/15 and 0/15 (rows forced into metrics)"], size=12)
    presenter(s, P[3])
    # 13 fine-tuning
    s = S[12]
    remove(by_name(s, "Text 4"))
    fit_picture(s, by_name(s, "Visual placeholder"), FIG / "fig10_finetuning_ladder.png")
    set_lines(by_name(s, "Text 6"), [f"+{isl(v1) - isl(base):.2f}"])
    set_lines(by_name(s, "Text 7"), ["island F1 vs base (n = 294 items)"])
    set_lines(by_name(s, "Text 8"), [
        f"**Ladder (same held-out cases):** base {f2(isl(base))} → 2-shot prompt {f2(isl(fs))} → adapter v1 {f2(isl(v1))}" + (f" → v2 {f2(isl(v2))}" if v2 else ""),
        f"**Why:** learns the 20-metric catalogue and verbatim evidence; prompt alone cannot (and costs {fs['island_extraction']['latency_s_median']:.0f} s vs {v1['island_extraction']['latency_s_median']:.0f} s)",
        f"**Cost:** v1 forgot other tasks: routing {f2(base['routing']['accuracy'])} → {f2(v1['routing']['accuracy'])}; v2 multi-task repairs it",
        "**Training:** 35 min (v1), ~90 min (v2) on an M4 Pro, ₹0"], size=12)
    presenter(s, P[3])
    # 14 automation
    s = S[13]
    au = D.agent_eval["workflow"]["automation"]
    for nm, val in (("Text 4", f"{au['automation_rate'] * 100:.0f}%"), ("Text 7", str(au["manual_interventions_in_run"])),
                    ("Text 10", "≈ 75 s"), ("Text 13", "₹0")):
        set_lines(by_name(s, nm), [val])
    set_lines(by_name(s, "Text 5"), [f"inputs fully automatic ({au['inputs_completed_without_manual_intervention']}/{au['inputs_attempted']})"])
    set_lines(by_name(s, "Text 11"), ["per document (LLM path; < 5 s rules)"])
    set_lines(by_name(s, "Text 14"), ["cost per document (local model)"])
    set_lines(by_name(s, "Text 15"), [
        f"**Run:** {au['llm_calls']} LLM calls · {au['model_outputs_rejected_by_gates']} model outputs rejected by gates · {au['duplicate_rows_skipped']} duplicates skipped · 0 retries needed",
        "**Remaining manual steps (once per source):** download from portals (no APIs), record URL + licence in the manifest, transcribe gold",
        "**Barriers to full automation:** no portal APIs or stable links, chart-only atlas pages, raster maps (out of scope), OCR on photos",
        "**Reproducible:** fresh clone → pip install → fetch (SHA-256) → 50 tests pass → quick start, on macOS / Linux / Windows (CI)"], size=13)
    presenter(s, P[2])
    # 15 live demo
    s = S[14]
    rows = []
    from agri.query.agent import QueryAgent
    qa = QueryAgent(config.DB_PATH, planner="rules")
    for r in demo_rows:
        rows.append([r["id"], r["question"][:62], r["type"].replace("_", "-").title(), short_answer(qa.ask(r["question"])),
                     "✓" if r["correct"] else "✗"])
    fill_table(by_name(s, "Table 0"), rows, size=10)
    set_lines(by_name(s, "Text 0"), [f"Live demonstration: 10 queries ({demo_ok}/10 correct in rehearsal)"])
    presenter(s, P[2])
    notes[15] = ("Run live in the terminal: `python scripts/ask.py --demo`, then `--show-source` on P1 to open D02 p1 with the cell boxed. "
                 "Then the app's Map tab. Never play a recording.")
    # 16 insight
    s = S[15]
    set_lines(by_name(s, "Text 0"), ["North & Middle Andaman: paddy −41% while arecanut area +32% (2021-22 → 2025-26)"])
    remove(by_name(s, "Text 4"))
    a1 = ANIM / "anim1_paddy_districts.mp4"
    if a1.exists():
        fit_movie(s, by_name(s, "Visual placeholder"), a1, FIG / "fig4_paddy_vs_arecanut_map.png")
    else:
        fit_picture(s, by_name(s, "Visual placeholder"), FIG / "fig4_paddy_vs_arecanut_map.png")
    set_lines(by_name(s, "Text 5"), [
        "**What it shows:** UT paddy 16,404 → 9,712 t; N&M Andaman is 98% of the fall; its arecanut area 2,527 → 3,338 ha; r = −0.83 (n = 5 years)",
        "**Also:** Port Blair vegetable prices peak Nov–Dec (onion +39% in Dec), tomato in Aug; 60% of farmers on 2 islands",
        "**Caveat:** correlation, not cause; 2025-26 from the Agriculture Department, earlier years from DES (agree to 0.01% where they overlap)"], size=12)
    presenter(s, P[0])
    notes[16] = "Click to play the district animation 2021-22 → 2025-26."
    # 17 errors
    s = S[16]
    fill_table(by_name(s, "Table 0"), [
        ["OCR (scans, photos)", "~1,400 cells", "photo of price table: 36/346 read"],
        ["Layout (footer as data)", "4 (fixed)", "phone number 232476 as holdings area"],
        ["Out-of-schema rows (new layout)", "23 / 30 sampled", "LPG connections → fertiliser"],
        ["Hallucination", "157 (gated)", "evidence not on page → dropped"],
        ["Source errors (publisher)", "2", "Shaheed farmers = Swaraj's 516; onion Nov-23 81.88 vs 57.50"]], size=10)
    set_lines(by_name(s, "Text 3"), [
        "**Method limits:** OCR loses isolated digits; 3B models are reliable only on narrow decisions; 5 yearly points cannot show causes",
        "**Implementation limits:** agents tied to seen layouts; no chart digitisation; approximate island points (±5 km); rule planner 0.80 on paraphrases",
        "**Threats to validity:** small gold (699 facts, 15 test queries); same-team annotation (from page images, before scoring); silver training labels; easy digital pages"], size=12)
    presenter(s, P[0])
    # 18 conclusion
    s = S[17]
    set_lines(by_name(s, "Text 3"), [
        f"**RQ1:** yes for digital files: macro F1 {f3(m['f1'])} (n = {fe['n_gold_total']}), provenance {f3(m['provenance_accuracy'])}, automation 20/20; scans remain hard (recall 0.10–0.52)",
        f"**RQ2:** yes, on the trained tasks: island F1 {f2(isl(base))} → {f2(isl(fs))} (prompt) → {f2(isl(v1))} (adapter); columns {f2(col(base))} → {f2(col(v1))}; multi-task v2 needed to avoid forgetting",
        f"**RQ3:** yes: {demo_ok}/10 live queries (≥ 2 spatial, ≥ 2 temporal, 2 provenance + Hindi); {f2(q_test)} on untouched paraphrases",
        "**Next:** layout-aware Indic OCR for scans; an agent for 'at a glance' compendia; chart digitisation; scheduled refresh when portals publish stable links"], size=15)
    presenter(s, P[0])
    # 19 team
    s = S[18]
    for k, (nm_name, nm_role, nm_body) in enumerate((("Text 4", "Text 5", "Text 6"), ("Text 8", "Text 9", "Text 10"), ("Text 12", "Text 13", "Text 14"))):
        mbr = TEAM["members"][k]
        set_lines(by_name(s, nm_name), [mbr["name"]])
        set_lines(by_name(s, nm_role), [mbr["role"]])
        set_lines(by_name(s, nm_body), [f"**Built:** {mbr['built']}", f"**Report:** {mbr['report']}", f"**Poster:** {mbr['poster']}",
                                        f"**Manual/video:** {mbr['manual']}"], size=9.5)
    # 20 refs
    s = S[19]
    set_lines(by_name(s, "Text 3"), [
        "[1] E. J. Hu et al., \"LoRA: Low-rank adaptation of large language models,\" ICLR, 2022.",
        "[2] T. Dettmers et al., \"QLoRA: Efficient finetuning of quantized LLMs,\" NeurIPS, 2023.",
        "[3] S. Yao et al., \"ReAct: Synergizing reasoning and acting in language models,\" ICLR, 2023.",
        "[4] A. Nassar et al., \"TableFormer: Table structure understanding with transformers,\" CVPR, 2022.",
        "[5] C. Auer et al., \"Docling technical report,\" arXiv:2408.09869, 2024.",
        "[6] Qwen Team, \"Qwen2.5 technical report,\" arXiv:2412.15115, 2024.",
        "[7] M. Pourreza and D. Rafiei, \"DIN-SQL: Decomposed in-context learning of text-to-SQL,\" NeurIPS, 2023.",
        "[8] DES A&N Administration, Basic Statistics; Island-wise Statistical Outline; price statements, 2023–2025.",
        "[9] DataMeet, Census 2011 / Survey of India boundaries, github.com/datameet/maps."], size=13)
    presenter(s, f"Presenter: {n1}")
    # 21 thanks
    s = S[20]
    set_lines(by_name(s, "Text 1"), [f"Repository: {TEAM['repo']} (tag {TEAM['tag']})  ·  Contact: {TEAM['contact']}"])
    for idx, title in HEADLINES.items():
        set_lines(by_name(S[idx], "Text 0"), [title])
    for i, slide in enumerate(S, 1):
        if i in notes:
            slide.notes_slide.notes_text_frame.text = notes[i]
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=TEMPLATE)
    ap.add_argument("--out", type=Path, default=OUT / "34_AN_PRESENTATION_v1.pptx")
    a = ap.parse_args()
    print(build(a.out, a.template))


if __name__ == "__main__":
    main()
