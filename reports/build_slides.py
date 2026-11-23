"""Build the Phase 3 talk (34_AN_PRESENTATION_v1.pptx): a custom 16:9 deck designed for the Phase 3 rubric.

T1 one message per slide, headline titles with numbers, slide 2 = hand-over plan;
T2 architecture, orchestration, models, schema with justification and alternatives;
T3 live 10-query slide (run live) with coverage; T4 geospatial animations (slides 6, 17, 18).

  python reports/build_slides.py [--out reports/out/34_AN_PRESENTATION_v1.pptx]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agri import config  # noqa: E402
from reports.build_report import Data, f2, f3  # noqa: E402
from reports.deck_kit import CORAL, INK, LINE, MEMBER, MUTED, PADDY, PALM, SEA, TEAL, TINT, TINT2, WHITE, Slide, new_prs  # noqa: E402

FIG, ANIM = config.FIGURES_DIR, config.FIGURES_DIR / "anim"
GEN = FIG / "slides"
TEAM = json.loads((ROOT / "reports" / "team.json").read_text())


def poster_frame(mp4: Path) -> Path:
    import imageio
    out = GEN / f"{mp4.stem}_poster.png"
    GEN.mkdir(parents=True, exist_ok=True)
    imageio.imwrite(out, imageio.get_reader(str(mp4)).get_data(0))
    return out


def problem_images() -> tuple[Path, str]:
    """Crop of the bilingual table as printed + the raw text a PDF extractor returns for it."""
    import pymupdf
    GEN.mkdir(parents=True, exist_ok=True)
    page = pymupdf.open(config.CORPUS_DIR / "Basic Statistics/Year 2024-25.pdf")[1]
    out = GEN / "problem_crop.png"
    page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=pymupdf.Rect(80, 85, 560, 225)).save(out)
    raw = " ".join(page.get_text("text", clip=pymupdf.Rect(80, 150, 330, 210)).split())[:120]
    return out, raw


def short_answer(a) -> str:
    r0 = a.rows[0] if a.rows else {}
    cite = f"[{r0.get('document_id')} p{r0.get('page')}]" if r0.get("document_id") else ""
    fmt = lambda v: f"{v:,.0f}" if abs(v) >= 100 else f"{v:g}"  # noqa: E731
    if a.tool == "rank_locations":
        return f"{r0['location'].replace(' (agri zone)', ' zone')}: {fmt(r0['value'])} {cite}"
    if a.tool == "nearby":
        return f"{r0['location']}: {fmt(r0['value'])} farmers, {r0['distance_km']} km {cite}"
    if a.tool == "time_series":
        s_ = a.summary
        return f"{fmt(s_['first'][1])} → {fmt(s_['last'][1])} ({s_['change_pct']:+.0f}%), peak {s_['peak'][0]}"
    if a.tool == "trace_value":
        return f"{fmt(r0['value'])} ← {r0['document_id']} p{r0['page']}, cell “{r0['value_raw']}”"
    if a.tool == "compare_sources":
        return f"{a.summary['periods_agreeing_within_1pct']} of {a.summary['periods_with_2plus_sources']} multi-source years agree"
    return a.text.split("\n")[0][:60]


def build(out: Path) -> Path:
    D = Data()
    fe, m = D.field, D.field["macro"]
    base, fs, v1, v2 = D.llm["base"], D.llm["base_fewshot2"], D.llm["qlora_v1"], D.llm["qlora_v2"]
    isl = lambda e: e["island_extraction"]["after_groundedness_gate"]["f1"]  # noqa: E731
    col = lambda e: e["column_mapping"]["column_accuracy"]  # noqa: E731
    qa = D.qa
    demo = json.loads((config.RESULTS_DIR / "phase3" / "query_eval_dev_hybrid_rules_v2.json").read_text())
    demo_rows = [r for r in demo["results"] if r["demo"]]
    demo_ok = sum(r["correct"] for r in demo_rows)
    n0, n1, n2 = [x["name"] for x in TEAM["members"]]
    prs = new_prs()
    n = 0

    def slide(bg=WHITE):
        nonlocal n
        n += 1
        return Slide(prs, bg)

    # ================================================================ 1 title
    s = slide(SEA)
    s.text(0.7, 0.75, 6.6, 0.4, ["CS F/U 407 ARTIFICIAL INTELLIGENCE  ·  TEAM 34  ·  PHASE 3"], size=13, color="8FD0DA", bold=True, fit=False)
    s.text(0.7, 1.3, 6.9, 2.3, ["From scattered PDFs to cited answers"], size=46, color=WHITE, face="Georgia", bold=True, smin=36, spacing=1.0)
    s.text(0.7, 3.55, 6.6, 1.0, ["An agentic, provenance-tracked agriculture knowledge base for the Andaman & Nicobar Islands"],
           size=20, color="CFE6EA", smin=16)
    yy = 4.85
    for nm, role in ((n0, "Model + Evaluation Lead"), (n1, "Source Lead"), (n2, "Data Engineering Lead")):
        s.circle(0.68, yy - 0.01, 0.4, MEMBER[nm], "".join(w[0] for w in nm.split()), size=12)
        s.text(1.15, yy - 0.02, 5.5, 0.42, [f"**{nm}**  ·  {role}"], size=15, color=WHITE, fit=False)
        yy += 0.5
    s.rect(7.75, 0.55, 5.0, 6.4, WHITE, radius=0.15)
    s.image(FIG / "poster" / "p_study_map.png", 0, 0, fit_box=(7.9, 0.7, 4.7, 6.1))
    s.text(0.7, 6.75, 6.5, 0.35, ["25 November 2026  ·  github.com/yababa-s/agriculture-assignment"], size=12, color="8FB3BC", fit=False)
    s.notes(f"{n1}: We are team 34; we built an agentic knowledge base for Andaman & Nicobar agriculture in which every number "
            "can be traced to the page it came from. (20 s)")

    # ================================================================ 2 plan / hand-overs
    s = slide()
    s.title("Six parts, three speakers, fifteen minutes")
    parts = [("0:00", "Problem, sources, study area", "1–6", n1, "Source Lead"),
             ("3:30", "Architecture, agents, models", "7–9", n0, "Model Lead"),
             ("6:00", "Knowledge base", "10", n2, "Data Eng. Lead"),
             ("7:00", "Evaluation and fine-tuning", "11–14", n0, "Evaluation Lead"),
             ("10:00", "Automation and live demo", "15–16", n2, "Data Eng. Lead"),
             ("12:30", "Insights, limits, conclusion", "17–22", n1, "Source Lead")]
    x, cw = 0.6, 1.95
    for t0, part, sl, who, role in parts:
        c = MEMBER[who]
        s.rect(x, 1.85, cw, 3.7, TINT)
        s.text(x + 0.15, 2.0, cw - 0.3, 0.5, [t0], size=24, color=c, face="Georgia", bold=True, fit=False)
        s.text(x + 0.15, 2.6, cw - 0.3, 1.2, [part], size=16, color=INK, bold=True, smin=13)
        s.text(x + 0.15, 3.85, cw - 0.3, 0.4, [f"slides {sl}"], size=13, color=MUTED, fit=False)
        s.circle(x + 0.15, 4.45, 0.42, c, "".join(w[0] for w in who.split()), size=12)
        s.text(x + 0.62, 4.38, cw - 0.7, 0.95, [f"**{who.split()[0]}**", role], size=13, color=INK, smin=10, para_gap=0.1)
        x += cw + 0.08
    s.text(0.6, 5.85, 12.1, 0.9, ["Six hand-overs in slide order, 15:00 in total. The live demonstration (slide 16) runs on the presenting "
                                   "laptop, never as a recording."], size=15, color=MUTED)
    s.footer(n, n1)
    s.notes("Hand-overs: Shikhar (1–6) → Suyash (7–9) → Abhineet (10) → Suyash (11–14) → Abhineet (15–16) → Shikhar (17–22).")

    # ================================================================ 3 problem
    s = slide()
    s.title("A&N farm data: 20 PDFs, 5 publishers, Hindi hidden in a legacy font")
    crop, raw = problem_images()
    s.rect(0.6, 1.6, 7.3, 5.2, TINT)
    s.text(0.85, 1.72, 6.8, 0.4, ["What the PDF shows (DES Basic Statistics 2024-25, p. 2)"], size=13, color=MUTED, bold=True, fit=False)
    s.image(crop, 0, 0, fit_box=(0.85, 2.12, 6.8, 2.5))
    s.text(0.85, 4.72, 6.8, 0.35, ["What a PDF extractor returns:"], size=13, color=MUTED, bold=True, fit=False)
    s.text(0.85, 5.05, 6.8, 0.75, [raw], size=13, color=CORAL, smin=11)
    s.text(0.85, 5.95, 6.8, 0.7, ["After our decoder:  नारियल Coconut · सुपारी Arecanut · काजू Cashewnut"], size=15, color=PALM,
           bold=True, fit=False)
    yy = 1.6
    for v, lab in (("20", "files · 6 modalities · 2 scripts"), ("3", "geographies: district, zone, island"),
                   ("0", "portals that cite where a number comes from")):
        s.stat(8.2, yy, 4.55, 1.12, v, lab, color=SEA, vsize=36, lsize=14)
        yy += 1.24
    s.text(8.2, 5.4, 4.55, 1.4, ["**Who asks:** analysts, researchers, extension staff. Which zone grows most paddy? How did prices "
                                 "move? Where does this number come from?"], size=14, color=INK)
    s.footer(n, n1)
    s.notes("The red text is what any PDF library returns for these Hindi labels: they are stored in the Kruti Dev font. "
            "Three geographies and no citations make the data hard to use. (60 s)")

    # ================================================================ 4 questions
    s = slide()
    s.title("Three questions: can agents extract, does LoRA help, can it answer live?")
    rqs = [("RQ1", "Extraction", "Can an agentic pipeline extract every number from A&N files with field F1 ≥ 0.95 and a page citation?", TEAL),
           ("RQ2", "Adaptation", "Does LoRA on a local 3B model beat the base model and a few-shot prompt on held-out documents?", PADDY),
           ("RQ3", "Answering", "Can the knowledge base answer spatial, temporal and provenance questions live, in English and Hindi?", PALM)]
    x = 0.6
    for code, head, q, c in rqs:
        s.rect(x, 1.65, 3.95, 3.3, TINT)
        s.circle(x + 0.25, 1.85, 0.75, c, code, size=15)
        s.text(x + 1.15, 1.95, 2.6, 0.5, [head], size=20, color=INK, face="Georgia", bold=True, fit=False)
        s.text(x + 0.25, 2.8, 3.45, 2.0, [q], size=16, color=INK, smin=13)
        x += 4.1
    s.text(0.6, 5.25, 12.1, 0.4, ["Contributions"], size=16, color=SEA, bold=True, fit=False)
    x, yc = 0.6, 5.75
    for c_ in ("7 specialist agents over 20 files", f"LoRA gain over prompting: +{isl(v1) - isl(fs):.2f} F1",
               f"provenance KB of {D.n_obs:,} numbers + maps", "3 spatio-temporal findings"):
        from reports.deck_kit import _font
        wpill = _font("Arial", True, 13).getlength(c_) / 720 + 0.36
        if x + wpill > 12.73:
            x, yc = 0.6, yc + 0.55
        x += s.pill(x, yc, c_, fill=SEA, size=13, h=0.42) + 0.15
    s.footer(n, n1)
    s.notes("Each question is answered with a number on slide 20. (40 s)")

    # ================================================================ 5 related work
    s = slide()
    s.title("No tool we tested decodes Kruti Dev or keeps cell-level provenance")
    t = D.tools

    def sc(tool, case):
        e = t.get(tool) or {}
        c = next((v for k, v in e.items() if k.startswith(case) and isinstance(v, dict)), None)
        return f"{c['correct']}/{c['of']}" if c else "—"
    rows = [["Approach", "Scanned / raster tables", "Hindi (Kruti Dev)", "Cell provenance", "Our test on the hardest pages"],
            ["pdfplumber", "✗", "✗", "✗", f"raster grid {sc('pdfplumber', 'C1')} · Kruti Dev {sc('pdfplumber', 'C3')}"],
            ["PyMuPDF", "✗", "✗", "✗", f"rotated headers {sc('pymupdf', 'C2')} · Kruti Dev {sc('pymupdf', 'C3')}"],
            ["Docling (layout + TableFormer)", "~", "✗", "✗", f"raster grid {sc('docling', 'C1')} · Kruti Dev {sc('docling', 'C3')}"],
            ["LLM agents (ReAct, LangGraph)", "via tools", "model-dependent", "only if designed", "base 3B routes 0.40 of files alone"],
            ["Text-to-SQL (Spider, DIN-SQL)", "—", "—", "✗", "not used: free SQL is fragile at 3B"],
            ["AgriAgent (this work)", "✓", "✓", "✓", f"{sc('ours', 'C1')} · {sc('ours', 'C2')} · {sc('ours', 'C3')} · F1 {f3(m['f1'])}"]]
    s.table(0.6, 1.65, 12.1, rows, [3.1, 2.0, 1.9, 1.9, 3.2], size=14, row_h=0.55, bold_col0=True, highlight_last=True)
    s.rect(0.6, 5.85, 12.1, 0.95, TINT2)
    s.text(0.8, 5.9, 11.7, 0.85, ["**Gap.** Methods exist for table structure and for agents. None decodes legacy fonts or exports "
                                   "provenance (an implementation gap); OCR recall on photos remains a method limit."], size=15, color=INK)
    s.footer(n, n1)
    s.notes("We measured these tools ourselves on our four hardest page types; the last row is our system. (50 s)")

    # ================================================================ 6 study area (animation)
    s = slide()
    s.title("20 files, 6 modalities, 3 districts, 31 islands, 2011 to 2026")
    a3 = ANIM / "anim3_island_farmers.mp4"
    s.rect(0.6, 1.6, 5.4, 5.25, TINT)
    s.movie(a3, poster_frame(a3), (0.7, 1.68, 5.2, 5.1))
    for k, (v, lab) in enumerate((("20", "files"), ("6", "modalities"), ("2", "languages"), ("3", "districts"), ("8", "agri zones"),
                                  ("31", "islands"))):
        s.stat(6.35 + (k % 3) * 2.15, 1.6 + (k // 3) * 1.42, 2.0, 1.27, v, lab, vsize=34, lsize=14)
    s.bullets(6.35, 4.6, 6.35, 2.2, [
        "**Years:** crops 2019-20 → 2025-26 · prices monthly 2019 → 2025 · census 2011, 2015-16",
        f"**Volume:** {D.pages} pages → {D.n_obs:,} observations, each with a citation",
        "**Licences:** 15 files without terms → academic use only; NRSC/Bhuvan non-commercial; D14 not redistributed"], size=14)
    s.footer(n, n1)
    s.notes("Click the map to play: farmers by island, 2022-23 → 2024-25. (45 s) → hand over to Suyash.")

    # ================================================================ 7 source -> agent
    s = slide()
    s.title("Seven agents, one per source group, each with the tools its format needs")
    yy = 1.62
    for src, fmt, ag, tools, by in (("Zone & district crop tables", "PDF · English", "matrix_table", "grid parser, rotated headers", "rule"),
                                    ("DES Basic Statistics", "PDF · Kruti Dev Hindi", "bilingual_table", "Kruti Dev decoder, column mapping", "model + rule"),
                                    ("Monthly price statements", "PDF · English", "price_table", "statement parser, year checks", "rule"),
                                    ("Island profiles", "prose · EN + HI", "island_profile", "line selector, evidence gate", "model"),
                                    ("Scheme memoranda, MoFPI", "narrative PDF", "narrative", "segmenter, fact extraction", "model"),
                                    ("Agriculture census screenshot", "PNG", "image_table", "Vision OCR, re-read empty cells", "rule"),
                                    ("LULC statistics / maps", "PDF table · raster", "lulc / skip", "table parser; rasters out of scope", "rule")):
        s.rect(0.6, yy, 4.0, 0.62, TINT)
        s.text(0.75, yy + 0.02, 3.8, 0.6, [f"**{src}**  ·  {fmt}"], size=13, color=INK, anchor="m", smin=10)
        s.arrow(4.65, yy + 0.31, 5.15, yy + 0.31, TEAL, 2)
        s.pill(5.2, yy + 0.12, ag, fill=SEA, size=13, h=0.4)
        s.text(7.75, yy + 0.02, 3.6, 0.6, [tools], size=13, color=INK, anchor="m", smin=10)
        s.pill(11.45, yy + 0.13, by, fill=PADDY if "model" in by else PALM, size=12, h=0.36)
        yy += 0.72
    s.footer(n, n0)
    s.notes("Model = the LLM decides; rule = fixed code. Every decision is logged as by=model or by=rule. (45 s)")

    # ================================================================ 8 architecture (native diagram)
    s = slide()
    s.title("A supervisor routes each file; validator feedback drives retries")
    boxes = [("Sources", "20 files +\nunseen", "FCE9D6"), ("Router", "supervisor:\nrule · fingerprint · LLM", "D6E9F0"),
             ("7 agents", "tools per\nformat", "DDEFE3"), ("Normaliser\n+ validator", "ids · ranges ·\nrow sums", "D6E9F0"),
             ("Knowledge base", "SQLite v2\n32,151 rows", "FBEBC4"), ("Query agent", "typed read-only\ntools → answer", "E6DDF2")]
    bw, gap, x = 1.8, 0.27, 0.6
    for k, (h_, sub, c) in enumerate(boxes):
        s.rect(x, 2.1, bw, 1.9, c, line=LINE)
        s.text(x + 0.08, 2.18, bw - 0.16, 0.85, [h_], size=16, color=INK, bold=True, align="c", anchor="m", smin=12)
        s.text(x + 0.08, 3.0, bw - 0.16, 0.9, [sub], size=12, color=MUTED, align="c", smin=10)
        if k < len(boxes) - 1:
            s.arrow(x + bw + 0.02, 3.05, x + bw + gap - 0.02, 3.05, SEA, 2.5)
        x += bw + gap
    s.arrow(0.6 + 3 * (bw + gap) + 0.5, 4.08, 0.6 + 2 * (bw + gap) + 1.2, 4.08, CORAL, 2)
    s.text(0.6 + 2 * (bw + gap) + 0.9, 4.12, 2.8, 0.35, ["retry with validator feedback (≤ 2)"], size=12, color=CORAL, fit=False)
    s.rect(2.65, 1.5, 6.4, 0.46, "F6DADD", radius=0.2)
    s.text(2.65, 1.5, 6.4, 0.46, ["Qwen2.5-3B + LoRA (local): routing · header meaning · facts · query plans"], size=13, color=CORAL,
           align="c", anchor="m", fit=False)
    x = 0.6
    for h_, body in (("Pattern", "Supervisor/router as a LangGraph state graph; every node, tool call and decision traced (JSONL + LangSmith)."),
                     ("Why", "Each source group needs different tools; a 3B model cannot hold seven tool sets in one prompt."),
                     ("Alternatives rejected", "One generalist agent (prompt overload) · fixed sequential pipeline (no per-file tools) · "
                                               "per-page sub-agents (more calls, no gain).")):
        s.rect(x, 4.7, 3.95, 2.1, TINT2)
        s.text(x + 0.2, 4.8, 3.6, 0.4, [h_], size=16, color=SEA, bold=True, fit=False)
        s.text(x + 0.2, 5.25, 3.6, 1.5, [body], size=14, color=INK, smin=11)
        x += 4.07
    s.footer(n, n0)
    s.notes("Walk left to right. A bad file ends as partial/failed/needs_review and never stops the batch. (70 s)")

    # ================================================================ 9 model vs code
    s = slide()
    s.title("A local 3B model decides meaning; fixed code writes every number")
    for x, fill, head, colr, items in ((0.6, "FCEFD2", "The model decides", PADDY,
                                         ["which agent, for an ambiguous unseen file", "what a column header means",
                                          "which facts an island profile states", "intent and slots of a question"]),
                                        (4.75, "DDEFE3", "Code decides", PALM,
                                         ["every number, unit and id", "evidence check: text must be on the page",
                                          "all SQL (typed, read-only tools)", "dedup, ranges, row sums"]),
                                        (8.9, TINT, "Model", SEA,
                                         ["Qwen2.5-3B-Instruct, 4-bit, on a laptop (no API, ₹0)", "LoRA r = 8 · scale 20 · 16 layers",
                                          "v1: 84 examples · v2: +198 planning and routing", "training documents only; eval documents never seen"])):
        s.rect(x, 1.6, 3.83 if x > 8 else 4.0, 3.55, fill)
        s.text(x + 0.2, 1.7, 3.5, 0.45, [head], size=18, color=colr, face="Georgia", bold=True, fit=False)
        s.bullets(x + 0.2, 2.25, 3.5, 2.8, items, size=15 if x < 8 else 14, dot=colr)
    s.text(0.6, 5.35, 12.1, 0.4, ["Alternatives considered"], size=16, color=SEA, bold=True, fit=False)
    s.bullets(0.6, 5.8, 12.1, 1.0, ["7B model: no room to fine-tune in 24 GB · API models: documents would leave the machine · "
                                    "free text-to-SQL: numbers could not be audited"], size=14, dot=MUTED)
    s.footer(n, n0)
    s.notes("Licence: the Qwen Research License allows research use; only adapter weights are released. (60 s) → hand over to Abhineet.")

    # ================================================================ 10 knowledge base
    s = slide()
    s.title(f"{D.n_obs:,} numbers, each traceable to its page and cell")
    cx, cy = 3.2, 3.85
    s.rect(cx - 1.25, cy - 0.65, 2.5, 1.3, "FBEBC4", line=LINE)
    s.text(cx - 1.2, cy - 0.6, 2.4, 1.2, ["**observation**", "value + citation"], size=15, color=INK, align="c", anchor="m", para_gap=0.1)
    for t_, sub, dx, dy in (("location", "+ lat / lon", -2.25, -1.75), ("commodity", "crops, items", 1.0, -1.75),
                            ("metric · unit", "base units", -2.25, 1.1), ("document · run · agent", "file, page, cell", 1.0, 1.1)):
        s.arrow(cx, cy, cx + dx + 0.875, cy + dy + 0.375, LINE, 1.5)
        s.rect(cx + dx, cy + dy, 1.75, 0.75, "DDEFE3", line=LINE)
        s.text(cx + dx + 0.05, cy + dy + 0.02, 1.65, 0.72, [f"**{t_}**", sub], size=12, color=INK, align="c", anchor="m", para_gap=0.05)
    s.rect(cx - 1.25, cy - 0.65, 2.5, 1.3, "FBEBC4", line=LINE)
    s.text(cx - 1.2, cy - 0.6, 2.4, 1.2, ["**observation**", "value + citation"], size=15, color=INK, align="c", anchor="m", para_gap=0.1)
    s.text(0.6, 6.05, 5.3, 0.8, ["Views: v_provenance (number → file, page, cell, agent, run) · v_conflict (two sources disagree)"],
           size=13, color=MUTED)
    from PIL import Image as _I
    prov = ROOT / "outputs" / "provenance" / "obs_1663_D02_p1.png"
    im = _I.open(prov)
    w_, h_ = im.size
    crop = GEN / "prov_crop.png"
    im.crop((int(w_ * 0.60), int(h_ * 0.585), int(w_ * 0.985), int(h_ * 0.655))).save(crop)
    s.rect(6.3, 1.6, 6.43, 2.6, TINT)
    s.text(6.5, 1.66, 6.0, 0.4, ["ask --show-source: coconut 2025-26 → D02 p1, cell boxed"], size=13, color=MUTED, bold=True, fit=False)
    s.image(crop, 0, 0, fit_box=(6.45, 2.05, 6.13, 2.05))
    n_loc = D.db.execute("SELECT COUNT(*) FROM location").fetchone()[0]
    s.bullets(6.35, 4.45, 6.35, 2.4, [f"**{n_loc} places:** UT → district → tehsil, 8 zones, 31 islands, with coordinates",
                                      "**Alias table** in English and Hindi; typed periods (agri year July–June, month, census)",
                                      "**Missing ≠ zero**; deterministic dedup key; id, range and row-sum checks"], size=14)
    s.footer(n, n2)
    s.notes("One row, one number, one citation. Schema v2 adds coordinates for spatial queries. (80 s) → hand over to Suyash.")

    # ================================================================ 11 evaluation setup
    s = slide()
    s.title(f"{fe['n_gold_total']} hand-transcribed facts and 45 queries, none used in training")
    for k, (v, lab) in enumerate(((str(fe["n_gold_total"]), "facts from held-out pages, transcribed by eye"), ("7", "agents, one region each"),
                                  ("30 + 15", "queries: dev / untouched test"), ("294 / 74", "LLM tasks: island items / columns"))):
        s.stat(0.6 + k * 3.07, 1.6, 2.92, 1.45, v, lab, vsize=34, lsize=13, color=[SEA, TEAL, PALM, PADDY][k])
    for x, head, items in ((0.6, "Metrics", ["field precision / recall / F1 with 95% bootstrap CI", "provenance accuracy (right page, value on it)",
                                              "tool selection (AgentEvals trajectory), task completion",
                                              "intent resolution and answer accuracy for queries", "automation rate"]),
                           (6.75, "Tools and choices", ["LangSmith datasets, experiments, traces; AgentEvals; Foundry evaluator checklist",
                                                        "skipped: fluency/coherence (templated answers), content safety (public statistics)",
                                                        f"gold checked by {n1} and {n2}; test queries written after the planner froze"])):
        s.rect(x, 3.3, 6.0 if x < 1 else 5.98, 3.5, TINT2)
        s.text(x + 0.2, 3.4, 5.6, 0.4, [head], size=17, color=SEA, bold=True, fit=False)
        s.bullets(x + 0.2, 3.9, 5.6, 2.85, items, size=14)
    s.footer(n, n0)
    s.notes("Held-out means: no page of these documents was used to train or tune anything. (50 s)")

    # ================================================================ 12 extraction results
    s = slide()
    s.title(f"Macro F1 {f3(m['f1'])} on {fe['n_gold_total']} held-out facts; every correct number cites its page")
    short = {"matrix_table_agent": "Matrix", "bilingual_table_agent": "Hindi", "price_table_agent": "Prices",
             "island_profile_agent": "Islands", "narrative_agent": "Narrative", "image_table_agent": "OCR image", "lulc_agent": "LULC"}
    s.bar_chart(0.6, 1.6, 7.2, 5.2, [f"{short[x['agent']]}\nn={x['n_gold']}" for x in fe["per_agent"]],
                {"F1": [x["f1"] for x in fe["per_agent"]]}, [TEAL], number_format="0.000", vmax=1.1, legend=False)
    rob = {c["case"][:2]: c for c in D.robust["cases"]}
    fa = {x["agent"]: x for x in fe["per_agent"]}
    yy = 1.6
    for h_, body, c in (("Digital pages are solved", f"6 of 7 agents at F1 ≥ 0.99; provenance accuracy {f3(m['provenance_accuracy'])}.", PALM),
                        ("The gold found 2 bugs", f"footer phone numbers stored as data; OCR dropped lone digits. Image agent 0.969 → {f3(fa['image_table_agent']['f1'])}.", PADDY),
                        ("Scans and photos are hard", f"photo of a price table: recall {f2(rob['T2']['recall'])}; scanned Hindi page {f2(rob['T4']['recall'])}. OCR, not routing.", CORAL)):
        s.rect(8.05, yy, 4.68, 1.65, TINT)
        s.circle(8.22, yy + 0.18, 0.36, c)
        s.text(8.7, yy + 0.1, 3.95, 0.45, [h_], size=16, color=INK, bold=True, fit=False)
        s.text(8.25, yy + 0.6, 4.35, 1.0, [body], size=13, color=INK, smin=11)
        yy += 1.78
    s.footer(n, n0)
    s.notes("Bars: field F1 per agent with the number of gold facts. Fresh files with new layouts are on slide 19. (70 s)")

    # ================================================================ 13 fine-tuning ladder
    s = slide()
    s.title(f"Fine-tuning beats prompting: island F1 {f2(isl(fs))} → {f2(isl(v1))}, queries {f2(qa('test', 'base_fewshot'))} → "
            f"{f2(qa('test', 'qlora_v2_zeroshot'))}")
    s.bar_chart(0.6, 1.6, 7.6, 5.2, ["Base\nzero-shot", "Base\nfew-shot prompt", "LoRA v1", "LoRA v2"], {
        "Island extraction F1 (n=294)": [isl(base), isl(fs), isl(v1), isl(v2)],
        "Column mapping acc. (n=74)": [col(base), col(fs), col(v1), col(v2)],
        "Query planning acc., test (n=15)": [qa("test", "base_zeroshot"), qa("test", "base_fewshot"), qa("test", "qlora_v1_fewshot"),
                                             qa("test", "qlora_v2_zeroshot")]}, [PALM, PADDY, TEAL], vmax=1.15, label_size=11)
    s.stat(8.45, 1.6, 4.28, 1.5, f"+{isl(v1) - isl(fs):.2f}", "island F1 over the best prompt, same held-out cases", color=PALM, vsize=40)
    s.stat(8.45, 3.25, 4.28, 1.5, f"+{qa('test', 'qlora_v2_zeroshot') - qa('test', 'base_fewshot'):.2f}",
           "query accuracy, v2 vs few-shot prompt", color=TEAL, vsize=40)
    s.rect(8.45, 4.9, 4.28, 1.9, "FBE3E6")
    s.text(8.6, 4.98, 4.0, 0.4, ["The cost"], size=15, color=CORAL, bold=True, fit=False)
    s.text(8.6, 5.38, 4.0, 1.4, [f"v1 forgot routing ({f2(base['routing']['accuracy'])} → {f2(v1['routing']['accuracy'])}) and query "
                                 "planning; v2 adds those tasks to training. Training: 35 min (v1), 90 min (v2), ₹0."], size=13, color=INK, smin=11)
    s.footer(n, n0)
    s.notes("Same held-out cases for every bar. The prompt also costs 18 s per island against 10 s for the adapter. (70 s)")

    # ================================================================ 14 query planner
    s = slide()
    s.title(f"The query agent scores {f2(qa('test', 'hybrid_rules_v2'))} on questions it never saw, always with a citation")
    labels = [("Rules", "rules"), ("Base", "base_zeroshot"), ("Few-shot", "base_fewshot"), ("LoRA v1", "qlora_v1_fewshot"),
              ("LoRA v2", "qlora_v2_zeroshot"), ("Deployed\nhybrid", "hybrid_rules_v2")]
    s.bar_chart(0.6, 1.6, 7.4, 5.2, [lb for lb, _ in labels], {"dev set (n=30)": [qa("dev", k) for _, k in labels],
                                                               "untouched test set (n=15)": [qa("test", k) for _, k in labels]},
                ["8CC5CE", SEA], vmax=1.15, label_size=11)
    yy = 1.65
    for k, (h_, sub) in enumerate((("Question", "English or Hindi"), ("Plan", "rules, else LoRA v2"), ("Typed tool", "read-only SQL"),
                                   ("Answer", "+ document, page, cell"))):
        s.circle(8.3, yy, 0.55, [TEAL, PADDY, PALM, SEA][k], str(k + 1), size=16)
        s.text(9.0, yy - 0.02, 3.7, 0.6, [f"**{h_}**  ·  {sub}"], size=15, color=INK, anchor="m", fit=False)
        if k < 3:
            s.arrow(8.575, yy + 0.58, 8.575, yy + 0.9, MUTED, 1.5)
        yy += 0.95
    s.text(8.3, 5.6, 4.43, 1.2, ["Rules were built on the dev set, so their 1.00 there is optimistic; the test bars are the honest numbers."],
           size=13, color=MUTED, italic=True)
    s.footer(n, n0)
    s.notes("Citation groundedness is 1.0 for every planner: numbers always come from SQL; errors are planning errors. (60 s) → Abhineet.")

    # ================================================================ 15 automation & reproducibility
    s = slide()
    au = D.agent_eval["workflow"]["automation"]
    s.title("20 of 20 files with no manual step; a fresh clone answers in 10 minutes")
    for k, (v, lab) in enumerate((("100%", "files fully automatic (20/20)"), ("0", "manual interventions in the run"),
                                  ("≈ 75 s", "per document, LLM path"), ("₹0", "cost: local model"))):
        s.stat(0.6 + k * 3.07, 1.6, 2.92, 1.45, v, lab, vsize=36, color=[SEA, TEAL, PALM, PADDY][k])
    x = 0.6
    for k, st in enumerate(("git clone", "pip install", "fetch + SHA-256", "50 tests pass", "first answer")):
        s.rect(x, 3.45, 2.2, 0.8, TINT if k < 4 else "DDEFE3")
        s.text(x, 3.45, 2.2, 0.8, [st], size=15, color=INK, bold=True, align="c", anchor="m", fit=False)
        if k < 4:
            s.arrow(x + 2.22, 3.85, x + 2.45, 3.85, SEA, 2)
        x += 2.47
    s.text(0.6, 4.35, 12.1, 0.4, ["Checked by CI on clean Ubuntu, macOS and Windows runners, and by a manual fresh-clone run."], size=13,
           color=MUTED, fit=False)
    s.bullets(0.6, 4.95, 6.0, 1.9, [f"**Run:** {au['llm_calls']} LLM calls · {au['model_outputs_rejected_by_gates']} model outputs "
                                    f"rejected by gates · {au['duplicate_rows_skipped']} duplicates skipped",
                                    "**Maintenance:** backup / restore, add-source, licence check, scheduled health check"], size=14)
    s.bullets(6.75, 4.95, 5.98, 1.9, ["**Still manual (once per source):** download (no portal APIs), manifest row, gold transcription",
                                      "**Barriers:** chart-only pages, raster maps, OCR on photos"], size=14)
    s.footer(n, n2)
    s.notes("Everything runs offline once fetched. (45 s)")

    # ================================================================ 16 live demo
    s = slide()
    s.title(f"Live: 10 questions, {demo_ok} of 10 correct in rehearsal")
    from agri.query.agent import QueryAgent
    qa_ = QueryAgent(config.DB_PATH, planner="rules")
    rows = [["#", "Question", "Type", "Answer (with citation)"]]
    for r in demo_rows:
        rows.append([r["id"], r["question"], r["type"].replace("_", "-"), short_answer(qa_.ask(r["question"]))])
    s.table(0.6, 1.55, 12.1, rows, [0.55, 5.6, 1.35, 4.6], size=11, row_h=0.43)
    s.rect(0.6, 6.42, 6.6, 0.45, SEA, radius=0.1)
    s.text(0.72, 6.42, 6.4, 0.45, ["$ python scripts/ask.py --demo     then  --show-source on P1"], size=13, color=WHITE, anchor="m",
           fit=False)
    s.pill(7.4, 6.47, "● LIVE, never a recording", fill=CORAL, size=12, h=0.36)
    s.footer(n, n2)
    s.notes("Run in the terminal at 20 pt: python scripts/ask.py --demo. Then the provenance question with --show-source to open "
            "D02 p1 with the cell boxed. Offer one question from the examiners. (2:30) → hand over to Shikhar.")

    # ================================================================ 17 insight 1 (geo animation)
    s = slide()
    s.title("North & Middle Andaman: paddy −41% while arecanut area grew +32%")
    a1 = ANIM / "anim1_paddy_districts.mp4"
    s.rect(0.6, 1.6, 7.4, 5.25, TINT)
    s.movie(a1, poster_frame(a1), (0.7, 1.68, 7.2, 5.1))
    for k, (v, lab, c) in enumerate((("−41%", "N&M paddy output, 2021-22 → 2025-26", CORAL), ("+32%", "N&M arecanut area, same years", PALM),
                                     ("98%", "of the UT's paddy decline is in N&M", SEA), ("r = −0.83", "paddy vs arecanut, n = 5 years", PADDY))):
        s.stat(8.25 + (k % 2) * 2.27, 1.6 + (k // 2) * 1.55, 2.18, 1.42, v, lab, color=c, vsize=30, lsize=12)
    s.rect(8.25, 4.8, 4.48, 2.05, TINT2)
    s.text(8.45, 4.88, 4.1, 1.9, ["**Caveat.** Correlation, not cause. 2025-26 comes from the Agriculture Department, earlier years "
                                  "from DES; where both report a year they agree to 0.01%."], size=13, color=INK, smin=11)
    s.footer(n, n1)
    s.notes("Click to play: paddy by district, year by year. Data: D03–D06, D02. (70 s)")

    # ================================================================ 18 insights 2-3
    s = slide()
    s.title("Vegetable prices peak in Nov–Dec; 60% of farmers live on two islands")
    a2 = ANIM / "anim2_price_calendar.mp4"
    s.rect(0.6, 1.6, 7.6, 3.55, TINT)
    s.movie(a2, poster_frame(a2), (0.68, 1.66, 7.44, 3.43))
    s.text(0.6, 5.25, 7.6, 1.6, ["**Port Blair, 2023–25 (n = 36 months × 10 items):** onion +39% above its mean in December, tomato "
                                 "+45% in August; eggs barely move (CV 0.08 vs 0.30). Supply is thinnest in the monsoon and in winter."],
           size=14, color=INK)
    s.rect(8.4, 1.6, 4.33, 5.25, TINT)
    s.image(FIG / "fig7_islands_farmers.png", 0, 0, fit_box=(8.5, 1.68, 4.13, 4.3))
    s.text(8.5, 6.0, 4.13, 0.85, ["Middle (8,730) + North Andaman (6,192) = 60% of 24,954 farmers (n = 16 islands)"], size=13, color=INK, smin=11)
    s.footer(n, n1)
    s.notes("Click the heatmap to watch it fill month by month. (45 s)")

    # ================================================================ 19 errors
    s = slide()
    s.title("Most errors are OCR on scans; two errors are in the source documents themselves")
    n_ocr = sum(c["known_values"] - c["correct"] for c in D.robust["cases"] if c.get("known_values"))
    rows = [["Error type", "Count", "Example"],
            ["OCR: cells not read on scans/photos", f"{n_ocr:,}", "photo of a price table: 36 of 346 values read"],
            ["Layout: footer read as data (fixed)", "4", "phone number 232476 stored as holdings area"],
            ["New layout: row forced into a metric", "23 / 30", "LPG connections mapped to fertiliser (fresh files)"],
            ["Model output not on the page", "157", "rejected by the evidence gate before loading"],
            ["Source error (publisher)", "2", "Shaheed farmers = Swaraj's 516; onion Nov-23 81.88 vs 57.50"]]
    s.table(0.6, 1.6, 7.6, rows, [3.0, 1.0, 3.6], size=12, row_h=0.62, bold_col0=True)
    for k, (h_, body, c) in enumerate((("Method limits", "OCR loses lone digits; 3B models are reliable only on narrow decisions; five yearly points cannot show causes.", CORAL),
                                       ("Our limits", "agents tied to layouts we saw (new 'at a glance' layouts: 0–5 of 15 right); no chart digitisation; island points ±5 km.", PADDY),
                                       ("Threats to validity", "small gold (699 facts, 15 test queries); same-team annotation from page images; easy digital pages.", TEAL))):
        yy = 1.6 + k * 1.75
        s.rect(8.4, yy, 4.33, 1.62, TINT)
        s.circle(8.55, yy + 0.15, 0.32, c)
        s.text(8.97, yy + 0.08, 3.7, 0.45, [h_], size=15, color=INK, bold=True, fit=False)
        s.text(8.55, yy + 0.55, 4.05, 1.05, [body], size=13, color=INK, smin=10.5)
    s.footer(n, n1)
    s.notes("Errors in the publications are kept and flagged (v_conflict), not silently corrected. (50 s)")

    # ================================================================ 20 conclusion (dark)
    s = slide(SEA)
    s.title("All three questions answered, with numbers")
    yy = 1.65
    for code, t_, c in (("RQ1", f"Yes for digital files: macro F1 {f3(m['f1'])} (n = {fe['n_gold_total']}), provenance {f3(m['provenance_accuracy'])}, "
                                "20/20 automatic. Scans: recall 0.10–0.52; new layouts 0–5 of 15.", TEAL),
                        ("RQ2", f"Yes on trained tasks: island F1 {f2(isl(base))} → {f2(isl(fs))} (prompt) → {f2(isl(v1))} (LoRA); queries "
                                f"{f2(qa('test', 'base_fewshot'))} → {f2(qa('test', 'qlora_v2_zeroshot'))}. Multi-task training avoids forgetting.", PADDY),
                        ("RQ3", f"Yes: {demo_ok}/10 live (3 spatial, 3 temporal, 2 provenance, Hindi); {f2(qa('test', 'hybrid_rules_v2'))} on unseen phrasings.", PALM)):
        s.circle(0.6, yy + 0.05, 0.8, c, code, size=15)
        s.text(1.65, yy, 11.0, 1.0, [t_], size=17, color=WHITE, anchor="m", smin=13)
        yy += 1.2
    s.text(0.6, 5.4, 12.1, 0.4, ["Next"], size=17, color="8FD0DA", bold=True, fit=False)
    s.text(0.6, 5.85, 12.1, 0.9, ["Layout-aware Indic OCR for scans · an agent for 'at a glance' compendia · chart digitisation · "
                                   "scheduled refresh once portals publish stable links"], size=16, color="CFE6EA")
    s.footer(n, n1)
    s.notes("(40 s) Then all three come forward for the contributions slide.")

    # ================================================================ 21 team
    s = slide()
    s.title("Who built what")
    x = 0.6
    for mbr in TEAM["members"]:
        s.rect(x, 1.6, 3.95, 5.25, TINT)
        s.circle(x + 0.25, 1.8, 0.75, MEMBER[mbr["name"]], "".join(w[0] for w in mbr["name"].split()), size=18)
        s.text(x + 1.15, 1.8, 2.7, 0.8, [f"**{mbr['name']}**", mbr["role"]], size=15, color=INK, para_gap=0.1, smin=12)
        s.text(x + 0.25, 2.75, 3.5, 2.15, [mbr["built"]], size=13, color=INK, smin=10.5)
        pres = {n0: "slides 7–9, 11–14", n1: "slides 1–6, 17–22", n2: "slides 10, 15–16 (live demo)"}[mbr["name"]]
        s.text(x + 0.25, 5.0, 3.5, 1.8, [f"**Presents:** {pres}", f"**Report:** {mbr['report']}", f"**Poster:** {mbr['poster']}",
                                          f"**Manual / video:** {mbr['manual']}"], size=12, color=INK, smin=10, para_gap=0.2)
        x += 4.07
    s.footer(n)

    # ================================================================ 22 thanks + refs
    s = slide(SEA)
    s.text(0.6, 0.8, 7.4, 1.2, ["Thank you · Questions"], size=44, color=WHITE, face="Georgia", bold=True, fit=False)
    s.text(0.6, 2.0, 7.4, 0.5, [f"{TEAM['repo']}  ·  tag {TEAM['tag']}"], size=15, color="8FD0DA", fit=False)
    s.text(0.6, 3.0, 7.4, 3.9, ["[1] E. J. Hu et al., LoRA, ICLR 2022", "[2] T. Dettmers et al., QLoRA, NeurIPS 2023",
                                "[3] S. Yao et al., ReAct, ICLR 2023", "[4] A. Nassar et al., TableFormer, CVPR 2022",
                                "[5] C. Auer et al., Docling technical report, 2024", "[6] Qwen Team, Qwen2.5 technical report, 2024",
                                "[7] M. Pourreza, D. Rafiei, DIN-SQL, NeurIPS 2023", "[8] DES A&N Administration, statistics 2021–2025",
                                "[9] DataMeet, Census 2011 / Survey of India boundaries"], size=13, color="CFE6EA", para_gap=0.25)
    s.rect(9.0, 1.3, 3.6, 3.6, WHITE, radius=0.15)
    s.image(FIG / "poster" / "qr_repo.png", 0, 0, fit_box=(9.2, 1.5, 3.2, 3.2))
    s.text(9.0, 5.0, 3.6, 0.4, ["Repository and results"], size=13, color="8FD0DA", align="c", fit=False)
    s.footer(n)

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    write_notes(prs)
    return out


def write_notes(prs) -> None:
    """Speaker notes per slide (kept out of the .pptx so Keynote can open it)."""
    from reports import deck_kit
    lines = ["# Speaker notes: 34_AN_PRESENTATION_v1.pptx", "",
             "Generated by `reports/build_slides.py`. Slide titles are the messages; notes say what to add aloud and when to hand over.", ""]
    titles = []
    for sl in prs.slides:
        t = [sh.text_frame.text for sh in sl.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
        titles.append(t[0] if t else "")
    import re as _re
    by_slide = {k: _re.sub(r"\s*\((?:\d+:\d+|\d+ s)\)", "", v) for k, v in deck_kit.NOTES}
    lines += ["Timing (15:00): slides 1–6 Shikhar 3:30 · 7–9 Suyash 2:30 · 10 Abhineet 1:00 · 11–14 Suyash 3:00 · "
              "15–16 Abhineet 2:30 (demo 2:00) · 17–22 Shikhar 2:30.", ""]
    for i, t in enumerate(titles, 1):
        lines += [f"## Slide {i}: {t.splitlines()[0][:90]}", "", by_slide.get(i, "(no note)"), ""]
    (ROOT / "docs" / "speaker_notes.md").write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "out" / "34_AN_PRESENTATION_v1.pptx")
    a = ap.parse_args()
    print(build(a.out))


if __name__ == "__main__":
    main()
