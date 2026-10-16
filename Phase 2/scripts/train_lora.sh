#!/usr/bin/env bash
# QLoRA fine-tune of Qwen2.5-3B-Instruct (4-bit base weights + LoRA adapters) with Apple MLX.
# Trains only on the assistant turn (--mask-prompt). Data: data/training/{train,valid}.jsonl
# built by scripts/build_datasets.py from TRAIN documents only.
set -euo pipefail
cd "$(dirname "$0")/.."
ADAPTER=${ADAPTER:-adapters/TEAMID_AN_qlora_v1}
ITERS=${ITERS:-250}
./.venv/bin/python -m mlx_lm lora \
  --model "${BASE_MODEL:-mlx-community/Qwen2.5-3B-Instruct-4bit}" \
  --train --data data/training \
  --fine-tune-type lora --num-layers 16 \
  --batch-size 1 --iters "$ITERS" --learning-rate 1e-4 \
  --mask-prompt --max-seq-length 2048 --grad-checkpoint \
  --steps-per-report 10 --steps-per-eval 50 --save-every 50 \
  --seed 407 \
  --adapter-path "$ADAPTER"
