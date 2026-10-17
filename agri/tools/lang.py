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


# Characters a correct Devanagari text layer never contains next to Hindi: other Brahmic-script
# blocks and private-use codes that broken font maps emit for conjuncts (e.g. 'ᭃेᮢफल' for 'क्षेत्रफल').
_BROKEN = re.compile(r"[\u1B00-\u1BFF\u1C80-\u1CFF\uA8E0-\uA8FF\uE000-\uF8FF\U000F0000-\U000FFFFD]")


def broken_devanagari_ratio(text: str) -> float:
    """Share of suspicious characters among Devanagari + suspicious characters (0 = clean)."""
    bad = len(_BROKEN.findall(text))
    deva = len(_DEVANAGARI.findall(text))
    return round(bad / (bad + deva), 3) if bad + deva else 0.0
