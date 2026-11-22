"""Architecture and entity-relationship diagrams (report Figures 2-3, slides 8 and 10).

  python scripts/make_diagrams.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from agri import config  # noqa: E402

FIG = config.FIGURES_DIR
plt.rcParams.update({"font.family": "DejaVu Sans", "savefig.dpi": 300})
COL = {"src": "#FCE9D6", "orch": "#D6E9F8", "agent": "#E3F1E3", "tool": "#F2F2F2", "db": "#FFF3C4", "query": "#EADCF5",
       "edge": "#555555", "model": "#F9D9D9"}


def box(ax, x, y, w, h, text, color, fs=9, bold=False, ec="#555555"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=color, ec=ec, lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal",
            wrap=True)


def arrow(ax, x1, y1, x2, y2, text="", style="-|>", color="#555555", ls="-", rad=0.0, fs=7.5):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=12, color=color, lw=1.2,
                                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, ha="center", fontsize=fs, color=color, style="italic")


def architecture():
    fig, ax = plt.subplots(figsize=(15, 8.6))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.6)
    ax.axis("off")
    # sources
    srcs = ["G1 matrix tables (PDF)", "G2 bilingual Kruti Dev\nHindi tables", "G3 monthly price tables",
            "G4 island profiles", "G5 narrative memoranda", "G6 screenshot table (image)", "G7 LULC statistics",
            "G8 raster maps (skipped)", "Unseen file\n(no manifest)"]
    ax.text(1.15, 8.3, "Sources (20 files + unseen)", ha="center", fontsize=10, fontweight="bold")
    for i, s in enumerate(srcs):
        box(ax, 0.1, 7.55 - i * 0.82, 2.1, 0.66, s, COL["src"], fs=7.8)
    # router
    box(ax, 2.8, 3.7, 1.9, 1.3, "Router\n(supervisor)\nmanifest rule ·\nfingerprint · LLM", COL["orch"], fs=8.5, bold=False)
    for i in range(9):
        arrow(ax, 2.2, 7.88 - i * 0.82, 2.8, 4.35, rad=0.0)
    ax.text(3.75, 5.2, "LangGraph state graph", ha="center", fontsize=8, color="#2E74B5", fontweight="bold")
    # agents
    agents = [("matrix_table_agent", "pdfplumber grid · rotated headers\nLLM column mapping (fallback)"),
              ("bilingual_table_agent", "Kruti Dev → Unicode decoder\nLLM column mapping"),
              ("price_table_agent", "comparative-statement parser\nyear/column checks"),
              ("island_profile_agent", "line selector · LLM extraction\ngroundedness gate"),
              ("narrative_agent", "scheme segmenter · LLM facts"),
              ("image_table_agent", "Vision OCR · grid rebuild\nre-OCR empty cells"),
              ("lulc_agent", "LULC table parser")]
    ax.text(6.6, 8.3, "Specialist extraction agents (tools)", ha="center", fontsize=10, fontweight="bold")
    for i, (a, t) in enumerate(agents):
        y = 7.45 - i * 1.0
        box(ax, 5.3, y, 2.6, 0.8, f"{a}\n{t}", COL["agent"], fs=7.2)
        arrow(ax, 4.7, 4.35, 5.3, y + 0.4)
    # normaliser / validator / loader
    box(ax, 8.6, 5.6, 1.9, 1.0, "Normaliser\naliases · fuzzy ·\nLLM fallback", COL["orch"], fs=8)
    box(ax, 8.6, 3.9, 1.9, 1.0, "Validator\nschema · ranges ·\nrow sums · dedup", COL["orch"], fs=8)
    box(ax, 8.6, 2.2, 1.9, 1.0, "Loader\nprovenance per\nnumber", COL["orch"], fs=8)
    for i in range(7):
        arrow(ax, 7.9, 7.85 - i * 1.0, 8.6, 6.1)
    arrow(ax, 9.55, 5.6, 9.55, 4.9)
    arrow(ax, 9.55, 3.9, 9.55, 3.2)
    arrow(ax, 8.6, 4.4, 7.9, 3.85, "retry with\nvalidator feedback", color="#D55E00", ls="--", rad=-0.3)
    # db
    box(ax, 10.95, 1.9, 2.4, 1.6, "SQLite knowledge base v2\n32,151 observations\nstar schema + provenance\n+ lat/lon (geo)",
        COL["db"], fs=7.6, bold=True)
    arrow(ax, 10.5, 2.7, 10.95, 2.7)
    # query layer
    box(ax, 11.1, 4.3, 2.0, 1.5, "Query Agent\nplanner: rules | LLM\n→ typed read-only tools\nrank · trend · trace ·\ncompare · nearby", COL["query"], fs=7.8)
    arrow(ax, 12.1, 3.5, 12.1, 4.3, "read-only SQL")
    box(ax, 13.5, 4.5, 1.4, 1.1, "CLI · Streamlit\napp · maps ·\nsource page", COL["query"], fs=7.8)
    arrow(ax, 13.1, 5.05, 13.5, 5.05)
    box(ax, 13.5, 6.4, 1.4, 0.9, "User question\n(EN / HI)", "#FFFFFF", fs=8)
    arrow(ax, 14.2, 6.4, 13.1, 5.6, rad=0.2)
    # model
    box(ax, 11.1, 6.8, 2.0, 1.2, "Qwen2.5-3B-Instruct\n(4-bit, MLX | HF)\n+ LoRA adapter v2", COL["model"], fs=8, bold=True)
    for (x, y) in ((4.7, 4.9), (7.9, 6.2), (10.5, 6.3), (12.1, 5.8)):
        arrow(ax, 11.1, 7.3, x, y, color="#B03A2E", ls=":", rad=0.15)
    ax.text(10.0, 7.75, "LLM calls (by=model)", fontsize=7.5, color="#B03A2E", style="italic")
    # traces
    box(ax, 5.3, 0.2, 7.0, 0.6, "Tracing: every node, tool call and decision (by=model | by=rule) → logs/traces/*.jsonl + LangSmith",
        COL["tool"], fs=8)
    ax.set_title("AgriAgent architecture: supervisor-routed specialist agents, shared normaliser/validator, provenance-first KB, query agent",
                 loc="left", fontsize=12, fontweight="bold")
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / "fig2_architecture.png", bbox_inches="tight")
    fig.savefig(FIG / "fig2_architecture.svg", bbox_inches="tight")
    plt.close(fig)
    print("  figures/fig2_architecture.png")


def er():
    T = {
        "source": ["source_id PK", "name", "portal_url", "license"],
        "document": ["document_id PK", "source_id FK", "file_name", "source_group", "languages", "sha256 UNIQUE", "license"],
        "extraction_run": ["run_id PK", "batch_id", "document_id FK", "agent_id FK", "model_name, adapter", "status, attempts",
                           "trace_path"],
        "agent": ["agent_id PK", "description", "version"],
        "observation": ["obs_id PK", "metric_id FK", "commodity_id FK", "location_id FK", "period_label, start, end", "dims (JSON)",
                        "value, unit_id FK", "value_raw, missing_reason", "document_id FK, page", "table_ref, row_label, col_label",
                        "run_id FK, agent_id FK", "confidence, validation", "dedup_key UNIQUE"],
        "location": ["location_id PK", "name, name_hi", "level", "parent_id FK (self)", "lgd_code", "lat, lon, geo_source  (v2)"],
        "commodity": ["commodity_id PK", "name, name_hi", "category", "is_aggregate"],
        "metric": ["metric_id PK", "name, domain", "default_unit FK"],
        "unit": ["unit_id PK", "symbol, dimension", "base_unit_id, to_base_factor"],
        "alias": ["alias, entity_type, entity_id PK", "lang (en|hi)", "origin (seed|llm|manual)"],
        "text_fact": ["fact_id PK", "subject, predicate, object", "document_id FK, page", "evidence (verbatim)"],
        "document_chunk": ["document_id FK, page", "text"],
        "rejected_record": ["run_id FK", "payload", "reason"],
    }
    pos = {"observation": (6.0, 3.2), "document": (2.6, 6.6), "source": (0.2, 7.6), "extraction_run": (6.0, 7.4),
           "agent": (9.4, 8.2), "location": (10.2, 4.8), "commodity": (10.2, 2.4), "metric": (10.2, 0.6), "unit": (6.4, 0.2),
           "alias": (13.2, 3.6), "text_fact": (0.2, 3.6), "document_chunk": (0.2, 1.7), "rejected_record": (2.9, 0.3)}
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")
    W, LH = 3.0, 0.26
    geo = {}
    for name, fields in T.items():
        x, y = pos[name]
        h = LH * (len(fields) + 1.2)
        color = "#FFF3C4" if name == "observation" else ("#D6E9F8" if name in ("document", "source", "extraction_run", "agent")
                                                        else "#E3F1E3" if name in ("location", "commodity", "metric", "unit", "alias")
                                                        else "#F2F2F2")
        ax.add_patch(FancyBboxPatch((x, y), W, h, boxstyle="round,pad=0.02", fc=color, ec="#555555"))
        ax.add_patch(plt.Rectangle((x, y + h - LH * 1.1), W, LH * 1.1, fc="#2E4E2E", ec="#555555"))
        ax.text(x + 0.1, y + h - LH * 0.6, name, color="white", fontsize=9.5, fontweight="bold", va="center")
        for i, f in enumerate(fields):
            ax.text(x + 0.1, y + h - LH * (1.7 + i), f, fontsize=7.6, va="center",
                    fontweight="bold" if "PK" in f else "normal", color="#B03A2E" if "(v2)" in f else "#222222")
        geo[name] = (x, y, W, h)

    def link(a, b, label="1..*"):
        xa, ya, wa, ha = geo[a]
        xb, yb, wb, hb = geo[b]
        p1 = (xa + wa / 2, ya + ha / 2)
        p2 = (xb + wb / 2, yb + hb / 2)
        ax.annotate("", xy=p2, xytext=p1, arrowprops={"arrowstyle": "-", "color": "#777777", "lw": 1, "shrinkA": 25, "shrinkB": 25})
        ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, label, fontsize=7, color="#777777")
    for a, b in (("observation", "document"), ("observation", "extraction_run"), ("observation", "location"),
                 ("observation", "commodity"), ("observation", "metric"), ("observation", "unit"), ("document", "source"),
                 ("extraction_run", "document"), ("extraction_run", "agent"), ("text_fact", "document"),
                 ("document_chunk", "document"), ("rejected_record", "extraction_run"), ("alias", "location"),
                 ("alias", "commodity"), ("metric", "unit")):
        link(a, b)
    ax.text(0.2, 9.7, "Knowledge-base schema v2: one fact table (observation) with full provenance; red = added in Phase 3",
            fontsize=12, fontweight="bold")
    ax.text(0.2, 9.35, "Views: v_provenance (number → file, page, cell, agent, run) · v_conflict (same fact, different value "
            "in two documents) · v_production · v_price", fontsize=9, color="#444444")
    fig.savefig(FIG / "fig3_er_diagram.png", bbox_inches="tight")
    fig.savefig(FIG / "fig3_er_diagram.svg", bbox_inches="tight")
    plt.close(fig)
    print("  figures/fig3_er_diagram.png")


if __name__ == "__main__":
    architecture()
    er()
