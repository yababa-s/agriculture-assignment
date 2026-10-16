"""Central configuration. Override any value with an environment variable of the same name."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Naming convention from the methodology: TEAMID_STATE_ARTIFACT_vN
TEAM_ID = os.getenv("TEAM_ID", "TEAMID")
STATE = "AN"  # Andaman & Nicobar Islands

CORPUS_DIR = Path(os.getenv("CORPUS_DIR", str(ROOT.parent / "AI Project Data Corpus")))
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "db" / f"{TEAM_ID}_{STATE}_knowledgebase_v1.sqlite")))
MANIFEST_PATH = ROOT / "data" / "manifest.csv"
TRACE_DIR = ROOT / "logs" / "traces"
GOLD_DIR = ROOT / "data" / "gold"
SPLITS_PATH = ROOT / "data" / "splits" / "splits.json"
RESULTS_DIR = ROOT / "eval" / "results"

# --- LLM -------------------------------------------------------------------
# Backend "mlx" runs locally on Apple Silicon. "none" disables every LLM call so
# each agent falls back to its rule-based path (used for ablations).
LLM_BACKEND = os.getenv("LLM_BACKEND", "mlx")
BASE_MODEL = os.getenv("BASE_MODEL", "mlx-community/Qwen2.5-3B-Instruct-4bit")
# Set ADAPTER_PATH to a LoRA adapter directory to run the fine-tuned model.
ADAPTER_PATH = os.getenv("ADAPTER_PATH") or None
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1500"))

# --- Orchestration ----------------------------------------------------------
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

# --- LangSmith --------------------------------------------------------------
# Tracing is sent to LangSmith only when LANGSMITH_API_KEY is set; local JSONL
# traces under logs/traces are always written.
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", f"{TEAM_ID}_{STATE}_agriagent")
LANGSMITH_ENABLED = bool(os.getenv("LANGSMITH_API_KEY"))
if LANGSMITH_ENABLED:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", LANGSMITH_PROJECT)
