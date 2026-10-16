"""Resolve corpus files in either the self-contained package or course repository."""
from __future__ import annotations

from pathlib import Path

PHASE2_ROOT = Path(__file__).resolve().parents[1]


def resolve_source_path(relative_path: str) -> Path:
    """Use the bundled corpus first, then the repository's existing Phase 1 folder."""
    relative = Path(relative_path)
    bundled = PHASE2_ROOT / "corpus" / relative
    if bundled.exists():
        return bundled
    # In the course repository, this package is placed at "Phase 2/Phase2_Submission".
    phase1 = PHASE2_ROOT.parents[1] / "Phase 1" / relative
    if phase1.exists():
        return phase1
    return bundled


def phase1_corpus_root() -> Path:
    """Return the corpus folder appropriate to the current checkout."""
    bundled = PHASE2_ROOT / "corpus"
    if bundled.is_dir():
        return bundled
    return PHASE2_ROOT.parents[1] / "Phase 1"
