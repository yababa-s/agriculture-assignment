"""Language and script detection for corpus documents."""
from __future__ import annotations

import re

from agri.tools.krutidev import has_kruti

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_languages(text: str) -> dict:
    """Return languages, scripts and whether Hindi is hidden behind a legacy font encoding."""
    deva = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    legacy = has_kruti(text)
    langs, scripts = [], []
    if latin:
        langs.append("en")
        scripts.append("Latin")
    if deva > 20 or legacy:
        langs.append("hi")
        scripts.append("Devanagari" + (" (Kruti Dev legacy encoding)" if legacy else ""))
    return {"languages": "+".join(langs) or "unknown", "scripts": "+".join(scripts) or "none", "legacy_font": legacy}
