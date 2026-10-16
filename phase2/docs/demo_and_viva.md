# Short demo and viva guide

## 8-minute demonstration

1. **Purpose (30 seconds):** “We turn the Phase 1 agriculture files into searchable evidence with a page citation.”
2. **Source map (1 minute):** show `data/manifest.csv`; every supplied file has a reader, pending status or explicit skip.
3. **Hindi example (1 minute):** show `Qlyksa dk uke` from the Basic Statistics PDF and the decoded `फसलों का नाम`. Explain that this is fixed font decoding, not model translation.
4. **Show the table agent (2 minutes):** after the full preflight, run `python phase2/query_db.py paddy-provenance`. Point from the printed 2024–25 Paddy production value to its exact PDF page/table/row and extraction run.
5. **Run the text agent (1 minute):** choose an island-wise PDF and show one exact numbered line linked to its page.
6. **Run checks (1 minute):** run `python phase2/evaluate.py`; open `evaluation/latest_evaluation.json` and explain the four direct values plus Hindi checks.
7. **Limitations (1 minute):** screenshot OCR and chart digitisation are pending; maps are skipped; AgentEvals/LangSmith and LLM fine-tuning were not run here.

Before presenting, run the full pipeline and tests on the presentation laptop. Do not show a sample database result until the latest run created it.

## Viva answers

**What is an agent here?** A small reader with one job: tables or page text. The manifest chooses it with fixed rules.

**What did you train?** No language model. The Hindi issue is a character-font mapping problem, so I tested a deterministic Kruti Dev decoder on examples from one Basic Statistics file and checked it on the other.

**Where does a number come from?** The observation stores the original text and the PDF name, page, table, row, column, reader and run. The provenance view joins those fields for a query.

**What is automated?** Once the files and manifest are prepared, routing, PDF reading, table-cell capture, database insertion and trace writing run automatically. Source discovery/download and human reference checking are not automated.

**What is still pending?** OCR for the census screenshot, chart reading for the atlas, complete numeric normalization for every table, and hosted evaluation with AgentEvals/LangSmith if those are mandatory in the course gate.

**Why not claim full coverage?** A source can be present and mapped while its extraction is pending or partial. The evaluation report shows those statuses separately.
