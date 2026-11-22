# Talk (15 ± 2 min), poster pitch (2 min), video (8–12 min) and viva preparation

Numbers below match `eval/results/` and the report. Rehearse with a timer; the rubric checks length, hand-overs and
whether the live queries run **live** (a recording scores 0 for T3).

## A. Presentation: who says what (matches slide 2)

| Slides | Presenter | Time | Say (one message per slide) |
|---|---|---|---|
| 1–2 | Abhineet | 0:45 | Title. "Three of us; this is who presents what." Point at the slide-2 table. |
| 3 | Abhineet | 1:00 | "Twenty PDFs from five publishers. Look at the red text: this is what a PDF extractor returns for the Hindi, because it is stored in the Kruti Dev font. Users want comparisons across places, trends, and the source of every number." |
| 4 | Abhineet | 0:40 | Three research questions, each answered with a number on slide 18. |
| 5 | Abhineet | 0:50 | "We tested the tools ourselves: Docling 0/8 on Kruti Dev, pdfplumber 0/6 on raster grids. Gap: no tool decodes legacy fonts or keeps cell-level provenance." |
| 6 | Abhineet | 0:45 | Click to play the island animation. "3 districts, 8 zones, 31 islands; 15 files have no stated licence, so they are flagged academic use only; D14 is not redistributed." → hand over to Suyash |
| 7 | Suyash | 0:50 | "One agent per source group, and each one has the tools its format needs." |
| 8 | Suyash | 1:10 | "Supervisor/router in LangGraph. We rejected a single generalist agent because a 3B model cannot hold seven tool sets in one prompt. A validator failure triggers a retry, and a model output whose evidence is not on the page is dropped." |
| 9 | Suyash | 1:00 | "Qwen2.5-3B runs locally, so no document leaves the machine. The chart shows recall per metric: for 'farmers' the base model gets 0.12 and the adapter 1.0. The model decides meaning; code writes every number." → Shikhar |
| 10 | Shikhar | 1:30 | "Every number is one row with its file, page, table, row, column, printed text, agent and run. Below is the cell the system opens for 'coconut 2025-26'. Missing is kept apart from zero, and re-runs are idempotent." → Suyash |
| 11 | Suyash | 0:50 | "Gold transcribed from page images of held-out pages: 699 facts and 45 queries. The test queries were written after the planner was frozen." |
| 12 | Suyash | 1:10 | "Macro F1 0.999 on digital pages. The gold evaluation found two bugs, footer phone numbers and dropped digits, and we fixed them. Scans and photos are the weak spot: recall 0.10–0.52." |
| 13 | Suyash | 1:10 | "Same held-out cases: base 0.27, 3-shot prompt 0.59, adapter 0.94. For queries the prompt gives 0.67 and adapter v2 0.93. The cost: v1 forgot routing, which is why v2 is multi-task." → Shikhar |
| 14 | Shikhar | 0:45 | "20/20 files automatic; ₹0; fresh clone to answer in 10 minutes on any OS, checked in CI." |
| 15 | Shikhar | 2:30 | **LIVE.** Run `python scripts/ask.py --demo` in a terminal at 20 pt font. Then `python scripts/ask.py --show-source "Which source and page did the 2025-26 coconut production figure for A&N come from?"`, which opens the page. If time allows, take one question from the examiners. → Abhineet |
| 16 | Abhineet | 1:10 | Click to play the paddy animation. "N&M Andaman paddy −41% while arecanut +32%; r = −0.83 over 5 years. A correlation, not a cause." |
| 17 | Abhineet | 0:50 | "Errors with counts. Two errors are in the source documents themselves. Method limits vs our limits." |
| 18 | Abhineet | 0:40 | Answer RQ1–RQ3 with numbers; next steps. |
| 19–21 | all | 0:20 | Contributions; thank you. |

Total ≈ 15:40. **Demo machine checklist:**
* run `python -m agri.cli status` before starting;
* warm the model once with `python scripts/ask.py --planner model "test"`;
* terminal font ≥ 20 pt;
* Wi-Fi off is fine, because everything is local;
* a second laptop with the same environment as backup, still running live.

## B. Poster pitch: 2 minutes, hand over at your own sections

* **Abhineet (sections 1, 2, 8), 45 s.** "A&N agriculture data is spread over 20 PDFs, and the Hindi is in a legacy font that extractors read as gibberish. We cover 3 districts, 8 zones and 31 islands. The headline finding: in North & Middle Andaman paddy fell 41% while arecanut area rose 32%."
* **Shikhar (sections 3, 5, 9), 35 s.** "A supervisor routes each file to one of seven agents. Every one of the 32,151 numbers keeps its page and cell. Our limit is OCR on photographed pages, and new layouts we have not seen."
* **Suyash (sections 4, 6, 7, 10–11), 40 s.** "A local 3B model with a LoRA adapter: island F1 0.27 → 0.94, and a prompt alone reaches only 0.59. Macro F1 0.999 on 699 hand-checked facts, and 10/10 live queries. Scan the QR code for the repository."

## C. Video: 34_AN_MANUAL_VIDEO_v1.mp4 (8–12 min, 1080p)

Record with QuickTime or OBS at 1920×1080 with the terminal at 20 pt, and zoom in when editing on every command
output. Start from a **fresh clone in a new user account or a new folder**. Each member narrates their own chapter. Put
the chapter timestamps in the video description.

| Time | Chapter (manual §) | Presenter | Screen | Narration (key lines) |
|---|---|---|---|---|
| 00:00 | Introduction (1) | Abhineet | report Figure 2, then the study-area map | what the system does, who it is for, what it does not do |
| 01:00 | Installation (2–4) | Shikhar | `git clone` → `git checkout phase3-submission` → venv → `pip install -r requirements.txt` → `cp .env.example .env` → `fetch_artifacts.py` (show the "sha256 verified" lines) → `pytest` (50 passed) → `python -m agri.cli status` | "no key or GPU needed; on Linux the LLM uses LLM_BACKEND=hf" |
| 04:00 | Processing a document (5.1–5.2) | Suyash | `run_pipeline.py --files data/test_unseen/hindi_area_production_2025-26.pdf` → batch table → `show_trace.py U01 --records 5` → LangSmith run page | "the router chose … because …; by=model vs by=rule" |
| 06:00 | Querying (5.3) | Suyash | spatial, temporal and Hindi questions; `--explain`; `--show-source` opens D02 p1; app Ask and Map tabs | "every line cites document and page" |
| 08:00 | Maintenance (6) | Shikhar | `agri.cli add-source` (on a copy), `backup`, `restore`, `check-licenses`, the scheduled workflow file | "back up before every write" |
| 09:45 | Troubleshooting + FAQ (7–8) | Abhineet | delete `db/*.sqlite`, run `ask.py` → the exact error → `fetch_artifacts.py --only database` → works | read one FAQ |
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

**Abhineet**
* Why Kruti Dev? How does the decoder work?
* Why these boundaries, and why not GADM? (Survey of India boundary required for maps of India.)
* How were the gold regions chosen and transcribed?
* Why is D14 not in the release?

**Shikhar**
* Why a star schema and a JSON `dims` column?
* How do you keep queries from writing? (Read-only URI plus a SELECT guard.)
* What does `dedup_key` contain?
* How does `restore` verify a backup?
* What fails on a fresh Windows machine, and how do you know? (CI matrix.)

**Hard questions**
* "Process this new document." Use `run_pipeline.py --files X.pdf`. Say honestly that new compendium layouts are mis-mapped (0–5/15 in our test) and that their records are flagged ⚠ unverified.
* "Is −41% real?" Two sources are joined; they agree to 0.01% where they overlap, but 2025-26 may be provisional.
