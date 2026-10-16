"""Create a small source-grounded train/evaluation split for the Hindi label decoder."""
from __future__ import annotations

import json
from pathlib import Path

import pdfplumber

PHASE2 = Path(__file__).resolve().parent
ROOT = PHASE2.parent

# These paired forms occur in the uploaded Basic Statistics PDFs. The Unicode side
# was checked against the English label printed beside it or is a direct short label.
TRAIN = [
    {"document": "basic statistics report 2023-24.pdf", "legacy": "Qlyksa dk uke", "unicode": "फसलों का नाम"},
    {"document": "basic statistics report 2023-24.pdf", "legacy": "Ukkfj;y", "unicode": "नारियल"},
    {"document": "basic statistics report 2023-24.pdf", "legacy": "/kku", "unicode": "धान"},
]
TEST = [
    {"document": "basic statistics report 2024-25.pdf", "legacy": "frygu", "unicode": "तिलहन"},
    {"document": "basic statistics report 2024-25.pdf", "legacy": "nf{k.k v.Meku", "unicode": "दक्षिण अण्डमान"},
]


def main() -> None:
    for split, rows in (("train", TRAIN), ("test", TEST)):
        for row in rows:
            source_path = ROOT / "corpus" / "basic stats" / row["document"]
            if not source_path.exists():
                raise FileNotFoundError(row["document"])
            with pdfplumber.open(source_path) as pdf:
                source_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if row["legacy"] not in source_text:
                raise ValueError(f"Example {row['legacy']!r} not found in its stated source: {row['document']}")
        path = PHASE2 / "training" / f"decoder_{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        print(f"{split}: {len(rows)} examples -> {path}")


if __name__ == "__main__":
    main()
