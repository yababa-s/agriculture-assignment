"""Build the A0 landscape poster (34_AN_POSTER_v1.pptx) from the course template.

Figures are re-drawn at their printed size with 20-28 pt text so they stay readable at 1.5 m.
  python reports/build_poster.py [--template PATH] [--out reports/out/34_AN_POSTER_v1.pptx]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402

from agri import config  # noqa: E402
from reports.build_report import Data, f2, f3  # noqa: E402
from reports.pptx_kit import by_name, fit_picture, remove, set_lines  # noqa: E402
from scripts import make_figures as MF  # noqa: E402

TEAM = json.loads((ROOT / "reports" / "team.json").read_text())
TEMPLATE = Path.home() / "Desktop" / "Phase 3 requirements" / "TEAMID_STATE_POSTER_template_landscape.pptx"
G = config.FIGURES_DIR / "poster"
FS = 22  # base figure font size in points at print scale


def _style():
    plt.rcParams.update({"font.size": FS, "axes.titlesize": FS + 2, "axes.labelsize": FS, "xtick.labelsize": FS - 2,
                         "ytick.labelsize": FS - 2, "legend.fontsize": FS - 2, "axes.spines.top": False,
                         "axes.spines.right": False, "font.family": "DejaVu Sans"})


def save(fig, name):
    G.mkdir(parents=True, exist_ok=True)
    p = G / f"{name}.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def study_map():
    _style()
    fig = plt.figure(figsize=(6.6, 7.6))
    ax = fig.add_axes([0.0, 0.0, 0.55, 1.0])
    MF.base_map(ax, {k: v[1] for k, v in MF.DIST.items()}, alpha=0.55)
    xy = MF.loc_xy()
    isl = [r["location_id"] for r in MF.q("SELECT location_id FROM location WHERE level='island' AND lat IS NOT NULL")]
    ax.scatter([xy[i][0] for i in isl], [xy[i][1] for i in isl], s=40, color="#222222", zorder=3, label="31 islands")
    zones = [r["location_id"] for r in MF.q("SELECT location_id FROM location WHERE level='agri_zone'")]
    ax.scatter([xy[z][0] for z in zones], [xy[z][1] for z in zones], s=260, marker="^", color="#D55E00", edgecolor="white",
               zorder=4, label="8 agri zones")
    for lid, (y, txt) in {"AN_NMA": (0.86, "N & M Andaman"), "AN_SA": (0.70, "South Andaman"), "AN_NIC": (0.54, "Nicobar")}.items():
        fig.text(0.58, y, "■ " + txt, fontsize=FS - 2, fontweight="bold", color=MF.DIST[lid][1])
    ax.set_xticks([])
    ax.set_yticks([])
    h, lab = ax.get_legend_handles_labels()
    fig.legend(h, lab, loc="upper left", bbox_to_anchor=(0.56, 0.5), fontsize=FS - 4, frameon=False)
    ins = fig.add_axes([0.58, 0.02, 0.4, 0.3])
    for _, g in MF.load_geo("india_outline.geojson"):
        MF.draw_geom(ins, g, facecolor="#DDDDDD", edgecolor="#888888", linewidth=0.4)
    ins.add_patch(plt.Rectangle((91.9, 6.6), 2.5, 7.3, fill=False, edgecolor="#D55E00", lw=2.5))
    ins.set_xlim(67, 98)
    ins.set_ylim(6, 37.5)
    ins.set_aspect("equal")
    ins.axis("off")
    return save(fig, "p_study_map")


def arch():
    _style()
    fig, ax = plt.subplots(figsize=(12.2, 5.0))
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0, 5)
    ax.axis("off")
    boxes = [(0.1, "20 files\nEN + HI", "#FCE9D6"), (2.15, "Router", "#D6E9F8"),
             (4.2, "7 agents\n+ tools", "#E3F1E3"), (6.25, "Validate", "#D6E9F8"),
             (8.3, "Know-\nledge\nbase", "#FFF3C4"), (10.35, "Query\nagent", "#EADCF5")]
    for x, t, c in boxes:
        ax.add_patch(FancyBboxPatch((x, 1.4), 1.75, 2.6, boxstyle="round,pad=0.04", fc=c, ec="#555555", lw=1.5))
        ax.text(x + 0.875, 2.7, t, ha="center", va="center", fontsize=FS - 4, fontweight="bold")
    for i in range(5):
        x = boxes[i][0] + 1.79
        ax.add_patch(FancyArrowPatch((x, 2.7), (x + 0.32, 2.7), arrowstyle="-|>", mutation_scale=30, color="#444444", lw=2.5))
    ax.add_patch(FancyArrowPatch((7.1, 1.35), (5.1, 1.35), arrowstyle="-|>", mutation_scale=25, color="#D55E00", lw=2.5,
                                 connectionstyle="arc3,rad=0.35"))
    ax.text(6.1, 0.35, "retry with validator feedback", ha="center", fontsize=FS - 4, color="#D55E00")
    ax.add_patch(FancyBboxPatch((2.2, 4.25), 7.8, 0.65, boxstyle="round,pad=0.03", fc="#F9D9D9", ec="#B03A2E"))
    ax.text(6.0, 4.57, "Qwen2.5-3B (local) + LoRA: routing · headers · facts · queries", ha="center", va="center",
            fontsize=FS - 4, color="#B03A2E")
    return save(fig, "p_arch")


def star():
    _style()
    fig, ax = plt.subplots(figsize=(6.2, 3.5))
    ax.set_xlim(0, 6.2)
    ax.set_ylim(0, 3.5)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((1.9, 1.05), 2.4, 1.4, boxstyle="round,pad=0.04", fc="#FFF3C4", ec="#555555", lw=1.5))
    ax.text(3.1, 1.75, "observation\nvalue + citation", ha="center", va="center", fontsize=FS - 3, fontweight="bold")
    for (x, y), t in {(0.05, 2.65): "location\n+ lat/lon", (4.45, 2.65): "commodity", (0.05, 0.05): "metric · unit",
                      (4.45, 0.05): "document\n· run · agent"}.items():
        ax.add_patch(FancyBboxPatch((x, y), 1.7, 0.8, boxstyle="round,pad=0.03", fc="#E3F1E3", ec="#555555"))
        ax.text(x + 0.85, y + 0.4, t, ha="center", va="center", fontsize=FS - 6)
        ax.plot([x + 0.85, 3.1], [y + 0.4, 1.75], color="#888888", lw=1.5, zorder=0)
    return save(fig, "p_star")


def eval_panel(D):
    _style()
    fe = D.field
    fig = plt.figure(figsize=(12.5, 4.9))
    a = fig.add_axes([0.06, 0.18, 0.42, 0.68])
    rows = fe["per_agent"]
    short = {"matrix_table_agent": "Matrix", "bilingual_table_agent": "Hindi", "price_table_agent": "Prices",
             "island_profile_agent": "Islands", "narrative_agent": "Narrative", "image_table_agent": "OCR img", "lulc_agent": "LULC"}
    a.bar(range(len(rows)), [r["f1"] for r in rows], color="#0072B2")
    for i, r in enumerate(rows):
        a.text(i, 0.06, f"n={r['n_gold']}", rotation=90, color="white", ha="center", va="bottom", fontsize=FS - 6, fontweight="bold")
    a.set_xticks(range(len(rows)))
    a.set_xticklabels([short[r["agent"]] for r in rows], rotation=35, ha="right", fontsize=FS - 6)
    a.set_ylim(0, 1.05)
    a.set_title(f"Field F1 by agent (macro {f3(fe['macro']['f1'])})", loc="left", fontsize=FS - 1, fontweight="bold")
    b = fig.add_axes([0.56, 0.18, 0.42, 0.68])
    isl = lambda e: e["island_extraction"]["after_groundedness_gate"]["f1"]  # noqa: E731
    labs = ["Base", "3-shot\nprompt", "LoRA"]
    v_isl = [isl(D.llm["base"]), isl(D.llm["base_fewshot2"]), isl(D.llm["qlora_v1"])]
    v_q = [D.qa("test", "base_zeroshot"), D.qa("test", "base_fewshot"), D.qa("test", "qlora_v2_zeroshot")]
    x = np.arange(3)
    b.bar(x - 0.2, v_isl, 0.4, color="#009E73", label="island F1 (n=294)")
    b.bar(x + 0.2, v_q, 0.4, color="#E69F00", label="query acc. (n=15)")
    for xi, v in zip(list(x - 0.2) + list(x + 0.2), v_isl + v_q):
        b.text(xi, v + 0.02, f"{v:.2f}", ha="center", fontsize=FS - 6)
    b.set_xticks(x)
    b.set_xticklabels(labs, fontsize=FS - 4)
    b.set_ylim(0, 1.15)
    b.legend(loc="upper left", fontsize=FS - 7, frameon=False)
    b.set_title("Fine-tuning vs prompting", loc="left", fontsize=FS - 1, fontweight="bold")
    return save(fig, "p_eval")


def hero(D):
    """Geospatial infographic: district paddy change map + zone bubbles + sparklines paddy vs arecanut."""
    _style()
    paddy = MF.series_by_location("production", "paddy", "district")
    areca = MF.series_by_location("area_cultivated", "arecanut", "district")
    zones = MF.series_by_location("production", "paddy", "agri_zone")
    years = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    change = {d: 100 * (paddy[d][years[-1]] - paddy[d][years[0]]) / paddy[d][years[0]] for d in paddy}
    fig = plt.figure(figsize=(15.2, 6.6))
    ax = fig.add_axes([-0.04, 0.0, 0.36, 1.0])
    cmap = plt.get_cmap("RdYlGn")
    MF.base_map(ax, {d: cmap(0.5 + max(-0.5, min(0.5, v / 100))) for d, v in change.items()}, alpha=0.9)
    ax.set_xticks([])
    ax.set_yticks([])
    xy = MF.loc_xy()
    for z, s in zones.items():
        if s.get("2025-26"):
            ax.scatter(*xy[z], s=80 + s["2025-26"] / 6, color="#C9A227", edgecolor="#222222", lw=1, alpha=0.85, zorder=4)
    ax.text(92.0, 7.0, "fill: % change\nbubbles: zone\noutput 2025-26", fontsize=FS - 7, va="bottom")
    for i, (d, (name, col)) in enumerate(MF.DIST.items()):
        y0 = 0.62 - i * 0.30
        a1 = fig.add_axes([0.36, y0, 0.27, 0.22])
        a2 = fig.add_axes([0.71, y0, 0.27, 0.22])
        pv = [paddy[d].get(y) for y in years]
        av = [areca[d].get(y) for y in years]
        a1.plot(range(5), pv, "-o", color="#C9A227", lw=3.5, ms=7)
        a2.plot(range(5), av, "-o", color="#2E7D32", lw=3.5, ms=7)
        for a_, v, u in ((a1, pv, "t"), (a2, av, "ha")):
            a_.set_xticks([0, 4])
            a_.set_xticklabels(["21-22", "25-26"], fontsize=FS - 7)
            a_.tick_params(axis="y", labelsize=FS - 8)
            pct = 100 * (v[-1] - v[0]) / v[0]
            a_.set_title(f"{pct:+.0f}%  ({v[0]:,.0f}→{v[-1]:,.0f} {u})", loc="left", fontsize=FS - 5, fontweight="bold",
                         color="#C0392B" if pct < 0 else "#2E7D32")
        a1.set_ylabel(name.replace(" & ", "&\n").replace("South ", "South\n"), fontsize=FS - 6, color=col, fontweight="bold")
    fig.text(0.36, 0.99, "Paddy production", fontsize=FS - 2, fontweight="bold", color="#C9A227")
    fig.text(0.71, 0.99, "Arecanut area", fontsize=FS - 2, fontweight="bold", color="#2E7D32")
    return save(fig, "p_hero")


def qr() -> Path:
    import qrcode
    G.mkdir(parents=True, exist_ok=True)
    p = G / "qr_repo.png"
    qrcode.make(TEAM["repo"], box_size=12, border=1).save(p)
    return p


def move_section(slide, n: int, top: float, height: float):
    """Move section n (frame, bar, number, heading and body/figure shapes inside it) to `top` with new frame `height`."""
    frame = by_name(slide, f"Section {n} frame")
    dy = Inches(top) - frame.top
    x0, x1, y0, y1 = frame.left, frame.left + frame.width, frame.top, frame.top + frame.height
    for sh in list(slide.shapes):
        if x0 - 10 <= sh.left <= x1 and y0 - 10 <= sh.top < y1 and sh.name != f"Section {n} frame":
            sh.top = sh.top + dy
    frame.top = Inches(top)
    frame.height = Inches(height)


def words(prs) -> int:
    n = 0
    for sh in prs.slides[0].shapes:
        if sh.has_text_frame:
            n += len(re.findall(r"[\w₹%+−.,/&()-]+", sh.text_frame.text))
    return n


def build(out: Path, template: Path) -> Path:
    D = Data()
    fe, m = D.field, D.field["macro"]
    prs = Presentation(str(template))
    s = prs.slides[0]
    names = [x["name"] for x in TEAM["members"]]
    base, v1 = D.llm["base"], D.llm["qlora_v1"]
    isl = lambda e: e["island_extraction"]["after_groundedness_gate"]["f1"]  # noqa: E731
    demo = json.loads((config.RESULTS_DIR / "phase3" / "query_eval_dev_hybrid_rules_v2.json").read_text())
    demo_ok = sum(r["correct"] for r in demo["results"] if r["demo"])

    set_lines(by_name(s, "Title"), ["From PDFs to cited answers: A&N agriculture knowledge base"])
    set_lines(by_name(s, "Authors"), [", ".join(names), f"Team {TEAM['team_id']}  ·  State: Andaman & Nicobar Islands  ·  CS F/U 407 Artificial Intelligence"])
    remove(by_name(s, "Text 4"))
    fit_picture(s, by_name(s, "QR placeholder"), qr(), pad=0.03)
    # 1
    set_lines(by_name(s, "Text 13"), [
        "A&N crop, price and island statistics are spread over 20 government PDFs: ruled tables, Hindi in the legacy Kruti Dev font, prose and screenshots. No portal can say where a number came from.",
        "**Objective:** extract every number with its page and cell, and answer spatial, temporal and provenance questions.",
        "**Contributions:** 7-agent pipeline · LoRA gain measured against prompting · provenance KB with maps"], size=24)
    # 2
    remove(by_name(s, "Text 20"))
    fit_picture(s, [x for x in s.shapes if x.name == "Figure placeholder"][0], study_map(), pad=0.01)
    set_lines(by_name(s, "Text 21"), ["**20** files", "**6** modalities", "**2** languages", "**3** districts", "**8** zones",
                                      "**31** islands", "2011 → 2025-26", "", "Prices · crops · islands · land use · budgets → 7 agents"], size=24)
    # 3
    remove(by_name(s, "Text 28"))
    fit_picture(s, [x for x in s.shapes if x.name == "Figure placeholder"][1], arch(), pad=0.01)
    set_lines(by_name(s, "Text 29"), ["Supervisor/router pattern (LangGraph): each file type needs its own tools; every decision traced as model or rule."], size=22)
    # 4
    set_lines(by_name(s, "Text 35"), [
        "**Tables, prices, LULC:** grid parser → exact numbers (rules)",
        "**Hindi tables:** Kruti Dev decoder → LLM maps columns",
        "**Island profiles:** LLM facts → evidence must be on the page",
        "**Screenshot:** OCR → re-read empty cells",
        "**Model:** Qwen2.5-3B, 4-bit, local · LoRA r=8 · v1: 84 ex. · v2: +200 query/routing ex."], size=24)
    # 5
    remove(by_name(s, "Text 42"))
    fit_picture(s, [x for x in s.shapes if x.name == "Figure placeholder"][2], star(), pad=0.01)
    set_lines(by_name(s, "Text 43"), [f"**{D.n_obs:,}** numbers", "Each keeps file, page, table, row, column, printed text, agent, run",
                                      "Normalised places, crops, units, periods"], size=24)
    # 6
    ph6 = [x for x in s.shapes if x.name == "Figure placeholder"][3:5]
    remove(by_name(s, "Text 50"))
    remove(by_name(s, "Text 52"))
    box = ph6[0]
    box.height = ph6[1].top + ph6[1].height - box.top
    remove(ph6[1])
    fit_picture(s, box, eval_panel(D), pad=0.01)
    set_lines(by_name(s, "Text 53"), [f"Gold: {fe['n_gold_total']} facts hand-transcribed from held-out pages; 15 untouched test queries. LangSmith + AgentEvals."], size=22)
    # 7
    set_lines(by_name(s, "Text 59"), [
        "**Spatial:** \"Which agri zone produced the most paddy in 2025-26?\" → Diglipur, 6,941 t [D02 p1]",
        "**Temporal:** \"UT paddy 2019-20 to 2025-26?\" → 17,982 → 9,712 t (−46%) [D03–D06, D02]",
        "**Provenance:** \"Source of 2025-26 coconut output?\" → D02 p1, cell 118.616 (highlighted)",
        f"**Accuracy:** {demo_ok}/10 live · {f2(D.qa('test', 'hybrid_rules_v2'))} on unseen phrasings · Hindi works"], size=24)
    # right column re-layout so the geospatial hero fits
    move_section(s, 11, 26.7, 3.6)
    move_section(s, 10, 22.0, 4.4)
    move_section(s, 9, 18.6, 3.1)
    frame8 = by_name(s, "Section 8 frame")
    frame8.height = Inches(12.1)
    set_lines(by_name(s, "Text 66"), [f3(m["f1"])])
    set_lines(by_name(s, "Text 67"), [f"macro F1, n = {fe['n_gold_total']}"])
    set_lines(by_name(s, "Text 69"), ["100%"])
    set_lines(by_name(s, "Text 70"), ["automation (20/20)"])
    set_lines(by_name(s, "Text 72"), [f"+{isl(v1) - isl(base):.2f}"])
    set_lines(by_name(s, "Text 73"), ["F1 from adapter (n=294)"])
    t74 = by_name(s, "Text 74")
    set_lines(t74, ["**North & Middle Andaman: paddy −41% while arecanut area +32% (2021-22 → 2025-26); r = −0.83, n = 5 years.**"], size=24)
    t74.height = Inches(1.3)
    hp = hero(D)
    pic = s.shapes.add_picture(str(hp), Inches(29.4), Inches(12.0), width=Inches(15.5))
    if pic.height > Inches(6.2):
        r = Inches(6.2) / pic.height
        pic.height, pic.width = Inches(6.2), int(pic.width * r)
    # 9
    set_lines(by_name(s, "Text 80"), ["**Method limit:** OCR misses digits on scans/photos (recall 0.10–0.52).",
                                      "**Our limit:** new 'at a glance' layouts mis-mapped. **Next:** Indic layout OCR."], size=24)
    by_name(s, "Text 80").height = Inches(2.0)
    # 10
    mm = TEAM["members"]
    set_lines(by_name(s, "Text 86"), [
        f"**{mm[0]['name']}** (Model + Eval Lead): orchestrator, LLM agents, adapters, query agent, evaluation · sections 4, 6, 7",
        f"**{mm[1]['name']}** (Source Lead): sources, manifest, Kruti Dev, geo layer, maps · sections 1, 2, 8",
        f"**{mm[2]['name']}** (Data Eng. Lead): schema, validator, query tools, reproducibility, app · sections 3, 5, 9"], size=24)
    by_name(s, "Text 86").height = Inches(3.3)
    # 11
    set_lines(by_name(s, "Text 92"), ["[1] Hu et al., LoRA, ICLR 2022 · [2] Dettmers et al., QLoRA, NeurIPS 2023",
                                      "[3] Yao et al., ReAct, ICLR 2023 · [4] Qwen Team, Qwen2.5 report, 2024",
                                      "[5] Nassar et al., TableFormer, CVPR 2022 · [6] DES A&N statistics 2021–2025"], size=20)
    set_lines(by_name(s, "Footer"), [f"{TEAM['team_id']}_AN_POSTER_v1  ·  Data: see manifest in repository  ·  Contact: {TEAM['contact']}"])
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    print(f"poster words: {words(prs)} (limit 800)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, default=TEMPLATE)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "out" / "34_AN_POSTER_v1.pptx")
    a = ap.parse_args()
    print(build(a.out, a.template))


if __name__ == "__main__":
    main()
