#!/usr/bin/env bash
# Rebuild every Phase 2 + Phase 3 artifact from the raw corpus. Takes ~4 h on an M-series Mac
# (most of it is LoRA training and the two LLM evaluation passes).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
ADAPTER=${ADAPTER:-adapters/34_AN_qlora_v1}

$PY scripts/build_manifest.py                      # data/manifest.csv
$PY scripts/init_db.py --fresh                     # schema + reference tables
$PY scripts/run_pipeline.py --no-llm               # rules-only pass (needed to build datasets)
$PY scripts/build_datasets.py                      # splits, gold sets, LoRA training data
ADAPTER=$ADAPTER ./scripts/train_lora.sh            # QLoRA adapter (train documents only)
$PY scripts/eval_llm_tasks.py --label base         # held-out tasks, base model
$PY scripts/eval_llm_tasks.py --label qlora_v1 --adapter "$ADAPTER"
$PY scripts/run_pipeline.py --fresh --adapter "$ADAPTER"   # production run: LLM + adapter
$PY scripts/eval_agents.py                          # agent/workflow evaluation of that batch
$PY scripts/sample_queries.py                       # docs/sample_queries.md
$PY experiments/tool_comparison.py --tools ours,pdfplumber,pymupdf
# Docling needs its own environment (torch): see experiments/tool_comparison.py
$PY scripts/langsmith_eval.py --adapter "$ADAPTER"  # only if LANGSMITH_API_KEY is set

# ---- Phase 3 additions
$PY scripts/build_geo.py --download                 # geospatial layer -> data/geo/
$PY -m agri.db.migrate                              # schema v2 (geo columns) on the database
$PY scripts/audit_db.py                             # data-quality audit (units, bounds, sums, conflicts)
$PY scripts/apply_corrections.py                    # logged corrections R1-R14 (docs/data_quality.md)
$PY scripts/audit_db.py                             # audit again after the corrections
$PY scripts/build_datasets_v2.py                    # multi-task training data (planning + routing)
DATA=data/training_v2 ADAPTER=adapters/34_AN_qlora_v2 ITERS=450 ./scripts/train_lora.sh
$PY scripts/eval_llm_tasks.py --label base_fewshot2 --few-shot 2 --tasks island,columns
$PY scripts/eval_llm_tasks.py --label qlora_v2 --adapter adapters/34_AN_qlora_v2
$PY scripts/eval_fields.py
$PY scripts/query_battery.py                        # 97-question coverage battery (dev-type)
$PY scripts/query_matrix.py                         # 1,093 generated questions: every measure x level x form
for S in dev test robust_dev robust_test; do
  $PY scripts/eval_queries.py --set $S --label rules --planner rules
  $PY scripts/eval_queries.py --set $S --label base_zeroshot --planner model --zero-shot
  $PY scripts/eval_queries.py --set $S --label base_fewshot --planner model
  $PY scripts/eval_queries.py --set $S --label qlora_v1_fewshot --planner model --adapter adapters/34_AN_qlora_v1
  $PY scripts/eval_queries.py --set $S --label qlora_v2_zeroshot --planner model --zero-shot --adapter adapters/34_AN_qlora_v2
  $PY scripts/eval_queries.py --set $S --label hybrid_rules_v2 --planner hybrid --zero-shot --adapter adapters/34_AN_qlora_v2
done
$PY scripts/make_figures.py && $PY scripts/make_eval_figures.py && $PY scripts/make_diagrams.py
$PY scripts/sample_queries.py && $PY scripts/make_demo_doc.py
for B in report manual slides poster; do $PY reports/build_$B.py; done
