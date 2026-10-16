"""Convert Hindi text typed in the legacy Kruti Dev 010 font into Unicode Devanagari.

DES A&N publications set Hindi in Kruti Dev, a font that draws Devanagari glyphs on
top of ASCII code points. The PDF text layer therefore contains ASCII gibberish
("Qlyksa dk uke" for "फसलों का नाम"). Generic OCR/LLM pipelines read it as
Latin noise, so we decode it with a glyph map plus the two reordering rules the
font relies on: the short-i matra (ि) is typed before its consonant cluster and
the reph (र्) is typed after the syllable it sits on.

The map follows the widely used open-source Kruti Dev converters (Rajbhasha
tables); it is ordered so multi-character sequences are replaced first.
"""
from __future__ import annotations

import re

_PAIRS: list[tuple[str, str]] = [
    ("ñ", "॰"), ("Q+Z", "QZ+"), ("sas", "sa"), ("aa", "a"), (")Z", "र्द्ध"), ("ZZ", "Z"),
    ("‘", "\""), ("’", "\""), ("“", "'"), ("”", "'"),
    ("å", "०"), ("ƒ", "१"), ("„", "२"), ("…", "३"), ("†", "४"), ("‡", "५"), ("ˆ", "६"), ("‰", "७"), ("Š", "८"), ("‹", "९"),
    ("¶+", "फ़्"), ("d+", "क़"), ("[+k", "ख़"), ("[+", "ख़्"), ("x+", "ग़"), ("T+", "ज़्"), ("t+", "ज़"),
    ("M+", "ड़"), ("<+", "ढ़"), ("Q+", "फ़"), (";+", "य़"), ("j+", "ऱ"), ("u+", "ऩ"),
    ("Ùk", "त्त"), ("Ù", "त्त्"), ("Dr", "क्त"), ("–", "दृ"), ("—", "कृ"), ("é", "न्न"), ("™", "न्न्"),
    ("=kk", "=k"), ("f=k", "f="),
    ("à", "ह्न"), ("á", "ह्य"), ("â", "हृ"), ("ã", "ह्म"), ("ºz", "ह्र"), ("º", "ह्"), ("í", "द्द"),
    ("{k", "क्ष"), ("{", "क्ष्"), ("=", "त्र"), ("«", "त्र्"),
    ("Nî", "छ्य"), ("Vî", "ट्य"), ("Bî", "ठ्य"), ("Mî", "ड्य"), ("<î", "ढ्य"), ("|", "द्य"), ("K", "ज्ञ"), ("}", "द्व"),
    ("J", "श्र"), ("Vª", "ट्र"), ("Mª", "ड्र"), ("<ªª", "ढ्र"), ("Nª", "छ्र"), ("Ø", "क्र"), ("Ý", "फ्र"),
    ("nzZ", "र्द्र"), ("æ", "द्र"), ("ç", "प्र"), ("Á", "प्र"), ("xz", "ग्र"), ("#", "रु"), (":", "रू"),
    ("v‚", "ऑ"), ("vks", "ओ"), ("vkS", "औ"), ("vk", "आ"), ("v", "अ"), ("b±", "ईं"), ("Ã", "ई"), ("bZ", "ई"),
    ("b", "इ"), ("m", "उ"), ("Å", "ऊ"), (",s", "ऐ"), (",", "ए"), ("_", "ऋ"),
    ("ô", "क्क"), ("d", "क"), ("Dk", "क"), ("D", "क्"), ("[k", "ख"), ("[", "ख्"), ("x", "ग"), ("Xk", "ग"), ("X", "ग्"),
    ("Ä", "घ"), ("?k", "घ"), ("?", "घ्"), ("³", "ङ"),
    ("pkS", "चै"), ("p", "च"), ("Pk", "च"), ("P", "च्"), ("N", "छ"), ("t", "ज"), ("Tk", "ज"), ("T", "ज्"),
    (">", "झ"), ("÷", "झ्"), ("¥", "ञ"),
    ("ê", "ट्ट"), ("ë", "ट्ठ"), ("V", "ट"), ("B", "ठ"), ("ì", "ड्ड"), ("ï", "ड्ढ"), ("M", "ड"), ("<", "ढ"), (".k", "ण"), (".", "ण्"),
    ("r", "त"), ("Rk", "त"), ("R", "त्"), ("Fk", "थ"), ("F", "थ्"), (")", "द्ध"), ("n", "द"), ("/k", "ध"), ("èk", "ध"),
    ("/", "ध्"), ("Ë", "ध्"), ("è", "ध्"), ("u", "न"), ("Uk", "न"), ("U", "न्"),
    ("i", "प"), ("Ik", "प"), ("I", "प्"), ("Q", "फ"), ("¶", "फ्"), ("c", "ब"), ("Cc", "ब"), ("C", "ब्"),
    ("Hk", "भ"), ("H", "भ्"), ("e", "म"), ("Ek", "म"), ("E", "म्"),
    (";", "य"), ("¸", "य्"), ("j", "र"), ("y", "ल"), ("Yk", "ल"), ("Y", "ल्"), ("G", "ळ"), ("o", "व"), ("Ok", "व"), ("O", "व्"),
    ("'k", "श"), ("'", "श्"), ("\"k", "ष"), ("\"", "ष्"), ("l", "स"), ("Lk", "स"), ("L", "स्"), ("g", "ह"),
    ("È", "ीं"), ("z", "्र"),
    ("Ì", "द्द"), ("Í", "ट्ट"), ("Î", "ट्ठ"), ("Ï", "ड्ड"), ("Ñ", "कृ"), ("Ò", "भ"), ("Ó", "्य"), ("Ô", "ड्ढ"), ("Ö", "झ्"),
    ("Ü", "श्"), ("Ük", "श"),
    ("‚", "ॉ"), ("ks", "ो"), ("kS", "ौ"), ("k", "ा"), ("h", "ी"), ("q", "ु"), ("w", "ू"), ("`", "ृ"), ("s", "े"), ("S", "ै"),
    ("a", "ं"), ("¡", "ँ"), ("%", "ः"), ("W", "ॅ"), ("•", "ऽ"), ("·", "ऽ"), ("~j", "्र"), ("~", "्"), ("\\", "?"), ("+", "़"),
    ("^", "‘"), ("*", "’"), ("Þ", "“"), ("ß", "”"), ("¼", "("), ("½", ")"), ("¿", "{"), ("À", "}"), ("¾", "="),
    ("A", "।"), ("-", "."), ("&", "-"), ("Œ", "॰"), ("]", ","), ("@", "/"),
]

# Longest Kruti sequences must win, but ties keep table order (the table already
# places "ks" before "k", "Dk" after "d", etc.). Build one alternation regex.
_ORDERED = sorted(enumerate(_PAIRS), key=lambda ip: (-len(ip[1][0]), ip[0]))
_MAP = {k: v for _, (k, v) in _ORDERED}
_RE = re.compile("|".join(re.escape(k) for _, (k, _v) in _ORDERED))

_CONS = "\u0915-\u0939\u0958-\u095F"
_I_MATRA = re.compile(rf"ि((?:[{_CONS}]़?्)*[{_CONS}]़?)")
_REPH = re.compile(rf"((?:[{_CONS}]़?्)*[{_CONS}]़?[ािीुूृेैोौंँ]*)Z")
# Leftover order artefact from "f" + "ि" sequences before an already-converted half form.
_FIX_ORDER = re.compile(r"्ि")


def krutidev_to_unicode(text: str) -> str:
    """Convert a Kruti Dev string to Unicode Devanagari. Latin words should be split out first."""
    out = _RE.sub(lambda m: _MAP[m.group(0)], text.replace("f", "ि"))
    out = _I_MATRA.sub(lambda m: m.group(1) + "ि", out)
    out = _REPH.sub(lambda m: "र्" + m.group(1), out)
    out = _FIX_ORDER.sub("ि्", out)
    return out


# Words that only appear in Kruti-encoded Hindi (frequent function words/terms in DES tables).
_KRUTI_MARKERS = re.compile(r"(?<![A-Za-z])(dk|ds|dh|vkSj|rFkk|}hi|dqy|Qly|{ks=Qy|mRiknu|lkaf\[;dh|v\.Meku|fudksckj|ukS|esa)(?![A-Za-z])")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z&/().'\- ]*[A-Za-z.)]|[A-Za-z]")


def has_kruti(text: str) -> bool:
    return len(_KRUTI_MARKERS.findall(text)) >= 2


def split_bilingual_label(label: str) -> tuple[str, str]:
    """Split a DES label like 'Ukkfj;y Coconut (M/nuts)' into (hindi_unicode, english).

    Hindi comes first in these documents. The Hindi prefix is the run of leading
    tokens that are not English words; it is converted only if it shows Kruti Dev
    signals, so plain English lines with rare words are left untouched.
    """
    label = " ".join(label.split())
    # glued forms such as 'Ukkfj;yCoconut' -> split before a known English word
    label = re.sub(r"(?<=[^\sA-Z(])([A-Z][a-z]{2,})", lambda m: (" " + m.group(1)) if _in_vocab(m.group(1).lower(), _vocabulary()) else m.group(1), label)
    tokens = label.split(" ")
    k = 0
    while k < len(tokens) and not _looks_english(tokens[k]):
        k += 1
    prefix, rest = tokens[:k], tokens[k:]
    # "<hindi> <English>" is the DES bilingual pattern, so a non-English prefix followed by
    # English is decoded; a line with no English part needs explicit Kruti signals.
    if not prefix or (not rest and not any(_kruti_signal(t) for t in prefix)):
        return "", label
    return krutidev_to_unicode(" ".join(prefix)), " ".join(rest)


_SIGNAL_CHARS = set("[]{};'\"|<>=~`^*¡¼½/}{±")


def _kruti_signal(tok: str) -> bool:
    if any(ch in _SIGNAL_CHARS for ch in tok) or _KRUTI_MARKERS.fullmatch(tok):
        return True
    letters = re.sub(r"[^A-Za-z]", "", tok)
    if not letters:
        return False
    if any(ch.isupper() for ch in letters[1:]) and not letters.isupper():
        return True  # eDdk, mRiknu, v.Meku
    return len(letters) <= 3 and not _in_vocab(letters.lower(), _vocabulary())


_DICT_PATH = "/usr/share/dict/words"
# Domain words missing from general dictionaries (crop names, units, abbreviations).
_DOMAIN_WORDS = {
    "paddy", "arecanut", "cashewnut", "seasam", "seasamum", "arhar", "chillies", "chilli", "turmeric", "nutmeg",
    "clove", "cinnamon", "brinjal", "lobiya", "lowky", "kundru", "turai", "jamikand", "arvi", "kumda", "tapioca",
    "chickoo", "sapota", "mace", "ixora", "muscanda", "marigold", "hibiscus", "vermi", "vermicompost", "nos",
    "mt", "ha", "hect", "hectares", "kg", "qtl", "nuts", "m/nuts", "n&m", "a&n", "pmfby", "rgrp", "pri", "pris",
    "kcc", "lulc", "ut", "dist", "misc", "prodn", "nicobar", "andaman", "kamorta", "nancowry", "diglipur",
    "mayabunder", "rangat", "katchal", "teressa", "chowra", "swaraj", "shaheed", "dweep", "baratang",
    "narcondam", "narcondum", "rutland", "pilomillow", "pulomillow", "tilongchang", "tilangchong", "tillangchong",
    "sentinel", "curlew", "aves", "landfall", "nicobarese", "ferrargunj", "campbell",
}
_KRUTI_ONLY = set("[]{};'\"|<>=~`^*¡¼½")
_vocab: set[str] | None = None


def _vocabulary() -> set[str]:
    global _vocab
    if _vocab is None:
        _vocab = set(_DOMAIN_WORDS)
        try:
            with open(_DICT_PATH) as f:
                # Keep words of length >= 3 only: short dictionary entries ("Qy", "dk") collide with Kruti tokens.
                _vocab |= {w.strip().lower() for w in f if len(w.strip()) >= 3}
        except OSError:
            pass
    return _vocab


def _looks_english(tok: str) -> bool:
    if not tok or any(ch in _KRUTI_ONLY for ch in tok):
        return False
    if tok.isdigit() or tok in {"&", "-", "(", ")"}:
        return True
    if re.search(r"[A-Za-z]{3,}.*\d|\d.*[A-Za-z]{3,}", tok):
        return True  # 'Fertilizers-Phospatic-1.05', 'Farmers-6192': English key-value tokens
    parts = [p for p in re.split(r"[^A-Za-z&]+", tok) if p]
    if not parts:
        return False
    vocab = _vocabulary()
    return all(_in_vocab(p.lower(), vocab) or (p.isupper() and len(p) <= 4) for p in parts)


def _in_vocab(word: str, vocab: set[str]) -> bool:
    # /usr/share/dict/words has no plurals, so also try singular forms.
    candidates = [word]
    if word.endswith("ies"):
        candidates.append(word[:-3] + "y")
    if word.endswith("es"):
        candidates.append(word[:-2])
    if word.endswith("s"):
        candidates.append(word[:-1])
    return any(c in vocab for c in candidates)
