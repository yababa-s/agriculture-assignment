#!/usr/bin/env bash
# Rebuild every Phase 2 artifact from the raw corpus. Takes ~1.5 h on an M-series Mac
# (most of it is LoRA training and the two LLM evaluation passes).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
ADAPTER=${ADAPTER:-adapters/TEAMID_AN_qlora_v1}

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
