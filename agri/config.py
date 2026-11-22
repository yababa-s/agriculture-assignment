"""Central configuration. Override any value with an environment variable of the same name."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from a local .env (git-ignored) without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ROOT / ".env")

# Naming convention from the methodology: TEAMID_STATE_ARTIFACT_vN
TEAM_ID = os.getenv("TEAM_ID", "34")
STATE = "AN"  # Andaman & Nicobar Islands

DB_VERSION = os.getenv("DB_VERSION", "v2")


def _path(value: str) -> Path:
    """Resolve a configured path: absolute as given, relative to the repository root otherwise."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else ROOT / p


# The corpus is fetched into data/raw by `python scripts/fetch_artifacts.py`.
CORPUS_DIR = _path(os.getenv("CORPUS_DIR", "data/raw"))
DB_PATH = _path(os.getenv("DB_PATH", f"db/{TEAM_ID}_{STATE}_knowledgebase_{DB_VERSION}.sqlite"))
GEO_DIR = ROOT / "data" / "geo"
FIGURES_DIR = ROOT / "figures"
BACKUP_DIR = _path(os.getenv("BACKUP_DIR", "backups"))
LOG_DIR = ROOT / "logs"
MANIFEST_PATH = ROOT / "data" / "manifest.csv"
TRACE_DIR = ROOT / "logs" / "traces"
GOLD_DIR = ROOT / "data" / "gold"
SPLITS_PATH = ROOT / "data" / "splits" / "splits.json"
RESULTS_DIR = ROOT / "eval" / "results"

# --- LLM -------------------------------------------------------------------
# Backend "mlx" runs locally on Apple Silicon. "none" disables every LLM call so
# each agent falls back to its rule-based path (used for ablations).
def _default_backend() -> str:
    """mlx on Apple Silicon when mlx-lm is installed, otherwise rules only (no model needed)."""
    import importlib.util
    import platform
    if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx_lm"):
        return "mlx"
    return "none"


LLM_BACKEND = os.getenv("LLM_BACKEND") or _default_backend()
BASE_MODEL = os.getenv("BASE_MODEL", "mlx-community/Qwen2.5-3B-Instruct-4bit")
# Full-precision checkpoint of the same model, used by the `hf` backend (transformers + peft).
HF_BASE_MODEL = os.getenv("HF_BASE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
# Set ADAPTER_PATH to a LoRA adapter directory to run the fine-tuned model.
ADAPTER_PATH = os.getenv("ADAPTER_PATH") or None
# Query planning uses adapter v2 (trained on planning; 0.93 on the untouched test set vs 0.67 for a 3-shot prompt).
_v2 = ROOT / "adapters" / "34_AN_qlora_v2"
QUERY_ADAPTER_PATH = os.getenv("QUERY_ADAPTER_PATH") or (str(_v2) if (_v2 / "adapters.safetensors").exists() else None)
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
