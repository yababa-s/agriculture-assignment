"""Small Kruti Dev 010 to Unicode decoder for labels in the supplied DES PDFs."""
from __future__ import annotations

import re

_MAP = {
    "Qlyksa": "फसलों", "dk": "का", "uke": "नाम", "Ukkfj;y": "नारियल",
    "liq": "सुपारी", "kjh": "री", "/kku": "धान", "frygu": "तिलहन",
    "nf{k.k": "दक्षिण", "v.Meku": "अण्डमान", "fudksckj": "निकोबार",
    "va-": "अं.", "rFkk": "तथा", "fu-": "नि.", "}hilewg": "द्वीपसमूह",
    "m-": "उ.", "vkSj": "और", "e/;": "मध्य", "dqy": "कुल",
}
_PHRASES = {"liq kjh": "सुपारी"}


def decode_kruti_label(label: str) -> str:
    """Decode known whole-word labels; preserve English text and unknown tokens."""
    for encoded, decoded in _PHRASES.items():
        label = label.replace(encoded, decoded)
    return " ".join(_MAP.get(token, token) for token in label.split())


def split_bilingual_label(label: str) -> tuple[str, str]:
    """Separate the leading legacy-font text from the English label in DES rows."""
    label = " ".join((label or "").split())
    tokens = label.split()
    english_terms = ("Coconut", "Arecanut", "Cashewnut", "Paddy", "Pulses", "Fruits", "Vegetables",
                     "Plantations", "Crop", "Fertilizers", "Rice", "Area", "Production")
    split_at = len(tokens)
    for i, token in enumerate(tokens):
        match = re.search(r"(" + "|".join(english_terms) + r")", token, re.I)
        if match:
            if match.start() > 0:
                tokens[i:i + 1] = [token[:match.start()], token[match.start():]]
            split_at = i
            break
    hindi = " ".join(tokens[:split_at])
    english = " ".join(tokens[split_at:])
    return decode_kruti_label(hindi), english
