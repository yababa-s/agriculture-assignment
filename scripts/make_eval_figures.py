"""Evaluation figures from eval/results (run after the evaluations): F1 by agent, the fine-tuning ladder,
query accuracy by planner. Missing result files are skipped.

  python scripts/make_eval_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from agri import config  # noqa: E402

R = config.RESULTS_DIR
P3 = R / "phase3"
FIG = config.FIGURES_DIR
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "savefig.dpi": 300})
SHORT = {"matrix_table_agent": "Matrix tables", "bilingual_table_agent": "Bilingual (Hindi)", "price_table_agent": "Prices",
         "island_profile_agent": "Island profiles", "narrative_agent": "Narrative", "image_table_agent": "Image (OCR)",
         "lulc_agent": "Land use"}


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(fig, name, note):
    fig.text(0.01, 0.005, note, fontsize=7, color="#666666")
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  figures/{name}.png")


def fig_f1_by_agent():
    e = load(P3 / f"field_eval_{config.DB_VERSION}.json")
    if not e:
        return
    rows = e["per_agent"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(rows))
    f1 = [r["f1"] for r in rows]
    lo = [r["f1"] - r["f1_ci95"][0] for r in rows]
    hi = [r["f1_ci95"][1] - r["f1"] for r in rows]
    ax.bar(x, f1, color="#0072B2", width=0.6)
    ax.errorbar(x, f1, yerr=[lo, hi], fmt="none", ecolor="#222222", capsize=4, lw=1.2)
    for i, r in enumerate(rows):
        ax.text(i, 0.03, f"n={r['n_gold']}", ha="center", color="white", fontsize=9, fontweight="bold")
        ax.text(i, r["f1"] + 0.012, f"{r['f1']:.3f}", ha="center", fontsize=9)
    ax.axhline(e["macro"]["f1"], color="#D55E00", ls="--", lw=1.3)
    ax.text(len(rows) - 0.5, e["macro"]["f1"] - 0.05, f"macro F1 {e['macro']['f1']:.3f}", color="#D55E00", ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT.get(r["agent"], r["agent"]) + f"\n{r['document_id']}" for r in rows], fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("field-level F1")
    ax.set_title(f"Extraction F1 by agent on held-out pages (n = {e['n_gold_total']} hand-transcribed facts)", loc="left")
    save(fig, "fig9_f1_by_agent", "Error bars: 95% bootstrap interval (2,000 resamples). Gold: data/gold/field_gold.json, "
         "island_profiles_D10.json. Database v2.")


def fig_ladder():
    labels, island, cols = [], [], []
    for lab, f in (("Base\nzero-shot", "llm_eval_base.json"), ("Base\n2-shot prompt", "llm_eval_base_fewshot2.json"),
                   ("+ adapter v1", "llm_eval_qlora_v1.json"), ("+ adapter v2", "llm_eval_qlora_v2.json")):
        e = load(R / f)
        if not e:
            continue
        labels.append(lab)
        island.append(e["island_extraction"]["after_groundedness_gate"]["f1"])
        cols.append(e["column_mapping"]["column_accuracy"])
    if not labels:
        return
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    x = np.arange(len(labels))
    b1 = ax.bar(x - 0.2, island, 0.4, color="#009E73", label="Island extraction F1 (n=294 items)")
    b2 = ax.bar(x + 0.2, cols, 0.4, color="#E69F00", label="Column mapping accuracy (n=74 columns)")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015, f"{b.get_height():.2f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.set_title("What fine-tuning adds over prompting (same held-out cases, raw model output)", loc="left")
    save(fig, "fig10_finetuning_ladder", "Held-out documents D10 (islands), D02 + D06 (columns). Qwen2.5-3B-Instruct 4-bit, greedy decoding.")


def fig_query():
    configs = [("Rules", "rules"), ("Base\nzero-shot", "base_zeroshot"), ("Base\nfew-shot", "base_fewshot"),
               ("Adapter v1\nfew-shot", "qlora_v1_fewshot"), ("Adapter v2\nzero-shot", "qlora_v2_zeroshot"),
               ("Hybrid\n(deployed)", "hybrid_rules_v2")]
    rows = []
    for lab, key in configs:
        d, t = load(P3 / f"query_eval_dev_{key}.json"), load(P3 / f"query_eval_test_{key}.json")
        if d or t:
            rows.append((lab, d["overall"]["answer_accuracy"] if d else np.nan, t["overall"]["answer_accuracy"] if t else np.nan))
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    x = np.arange(len(rows))
    b1 = ax.bar(x - 0.2, [r[1] for r in rows], 0.4, color="#56B4E9", label="dev set (n=30)")
    b2 = ax.bar(x + 0.2, [r[2] for r in rows], 0.4, color="#0072B2", label="untouched test set (n=15)")
    for bars in (b1, b2):
        for b in bars:
            if not np.isnan(b.get_height()):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015, f"{b.get_height():.2f}", ha="center", fontsize=8.5)
    ax.set_xticks(x)
    ax.set_xticklabels([r[0] for r in rows], fontsize=9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("answer accuracy")
    ax.legend(fontsize=9, frameon=False, loc="upper right")
    ax.set_title("Query agent: answer accuracy by planner", loc="left")
    save(fig, "fig11_query_accuracy", "Rules were developed on the dev set; the test set was written afterwards and never used for development.")


def main() -> None:
    print("[eval]")
    fig_f1_by_agent()
    fig_ladder()
    fig_query()


if __name__ == "__main__":
    main()
