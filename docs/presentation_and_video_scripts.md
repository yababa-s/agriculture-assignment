# Talk (15 ± 2 min), poster pitch (2 min), video (8–12 min) and viva preparation

Numbers below match `eval/results/` and the report. Rehearse with a timer; the rubric checks length, hand-overs and
whether the live queries run **live** (a recording scores 0 for T3).

## A. Presentation: who says what (matches slide 2)

The deck is `reports/out/34_AN_PRESENTATION_v1.pptx`: a 16:9 deck with 22 slides, built by `reports/build_slides.py`, which opens in
PowerPoint and Keynote. Notes for each slide are in [speaker_notes.md](speaker_notes.md). They are kept out of the
.pptx because Keynote cannot import the notes master that python-pptx generates.

| Slides | Presenter | Time | Content |
|---|---|---|---|
| 1–6 | Shikhar | 0:00–3:30 | title, talk plan, problem (Kruti Dev example), research questions, related work and gap, study area (click to play the island animation) |
| 7–9 | Suyash | 3:30–6:00 | source → agent mapping, architecture (pattern, why, rejected alternatives), model vs code and the adapter |
| 10 | Abhineet | 6:00–7:00 | knowledge base and provenance (the cell boxed on the page) |
| 11–14 | Suyash | 7:00–10:00 | evaluation setup, F1 by agent, fine-tuning vs prompting, query planners |
| 15–16 | Abhineet | 10:00–12:30 | automation and reproducibility; **live demo, 2:00, in a terminal** |
| 17–22 | Shikhar | 12:30–15:00 | paddy-to-arecanut animation, prices and islands animation, errors and limits, conclusion, team, thanks |

Demo machine checklist:
* run `python -m agri.cli status` before starting;
* warm up the model once with `python scripts/ask.py --planner model "test"`;
* terminal font at 20 pt or more;
* Wi-Fi off is fine, because everything runs locally;
* bring a second laptop with the same environment as a backup, still running live.

The videos on slides 6, 17 and 18 open on their final frame and play the build-up when clicked.

## B. Poster pitch: 2 minutes, hand over at your own sections

* **Shikhar (sections 1, 2, 8), 45 s.** "A&N agriculture data is spread over 20 PDFs, and the Hindi is in a legacy font that extractors read as gibberish. We cover 3 districts, 8 zones and 31 islands. The headline finding: in North & Middle Andaman paddy fell 41% while arecanut area rose 32%."
* **Abhineet (sections 3, 5, 9), 35 s.** "A supervisor routes each file to one of seven agents. Every one of the 32,151 numbers keeps its page and cell. Our limit is OCR on photographed pages, and new layouts we have not seen."
* **Suyash (sections 4, 6, 7, 10–11), 40 s.** "A local 3B model with a LoRA adapter: island F1 0.27 → 0.94, and a prompt alone reaches only 0.59. Macro F1 0.999 on 699 hand-checked facts, and 10/10 live queries. Scan the QR code for the repository."

## C. Video: 34_AN_MANUAL_VIDEO_v1.mp4 (8–12 min, 1080p)

Record with QuickTime or OBS at 1920×1080 with the terminal at 20 pt, and zoom in when editing on every command
output. Start from a **fresh clone in a new user account or a new folder**. Each member narrates their own chapter. Put
the chapter timestamps in the video description.

| Time | Chapter (manual §) | Presenter | Screen | Narration (key lines) |
|---|---|---|---|---|
| 00:00 | Introduction (1) | Shikhar | report Figure 2, then the study-area map | what the system does, who it is for, what it does not do |
| 01:00 | Installation (2–4) | Abhineet | `git clone` → `git checkout phase3-submission` → venv → `pip install -r requirements.txt` → `cp .env.example .env` → `fetch_artifacts.py` (show the "sha256 verified" lines) → `pytest` (50 passed) → `python -m agri.cli status` | "no key or GPU needed; on Linux the LLM uses LLM_BACKEND=hf" |
| 04:00 | Processing a document (5.1–5.2) | Suyash | `run_pipeline.py --files data/test_unseen/hindi_area_production_2025-26.pdf` → batch table → `show_trace.py U01 --records 5` → LangSmith run page | "the router chose … because …; by=model vs by=rule" |
| 06:00 | Querying (5.3) | Suyash | spatial, temporal and Hindi questions; `--explain`; `--show-source` opens D02 p1; app Ask and Map tabs | "every line cites document and page" |
| 08:00 | Maintenance (6) | Abhineet | `agri.cli add-source` (on a copy), `backup`, `restore`, `check-licenses`, the scheduled workflow file | "back up before every write" |
| 09:45 | Troubleshooting + FAQ (7–8) | Shikhar | delete `db/*.sqlite`, run `ask.py` → the exact error → `fetch_artifacts.py --only database` → works | read one FAQ |
| 10:40 | Wrap-up | all | README results table | where to find the report, manual and results |

## D. Viva: questions to prepare (Phase 3 additions)

**Everyone**
* Explain the pipeline in one minute.
* Where does a number come from? Show it with `--show-source`.

**Suyash**
* Why did v1 break routing? (Catastrophic forgetting: it answers in the trained JSON format.)
* What did fine-tuning add over prompting? (+0.34 island F1, +0.27 query accuracy on the same held-out cases.)
* Is the gold independent of the silver training labels? (Gold is transcribed from page images; the training data comes from TRAIN documents only.)
* Why is the hybrid test score optimistic? (Its confidence rule was defined after the first test run; v2 alone gets 0.93.)

**Shikhar**
* Why Kruti Dev? How does the decoder work?
* Why these boundaries, and why not GADM? (Survey of India boundary required for maps of India.)
* How were the gold regions chosen and transcribed?
* Why is D14 not in the release?

**Abhineet**
* Why a star schema and a JSON `dims` column?
* How do you keep queries from writing? (Read-only URI plus a SELECT guard.)
* What does `dedup_key` contain?
* How does `restore` verify a backup?
* What fails on a fresh Windows machine, and how do you know? (CI matrix.)

**Hard questions**
* "Process this new document." Use `run_pipeline.py --files X.pdf`. Say honestly that new compendium layouts are mis-mapped (0–5/15 in our test) and that their records are flagged ⚠ unverified.
* "Is −41% real?" Two sources are joined; they agree to 0.01% where they overlap, but 2025-26 may be provisional.
