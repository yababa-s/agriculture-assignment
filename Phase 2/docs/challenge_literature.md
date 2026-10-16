# Challenge and supporting literature

## The challenge we focused on

**Reading heterogeneous Indian government statistics PDFs faithfully, where the hard part is not OCR
but *layout and encoding traps*, while keeping units and cell-level provenance.**

What we actually hit in our corpus (all reproducible, see `experiments/tool_comparison.py`):

| Trap | Where | What goes wrong |
|---|---|---|
| **Hindi in a legacy font (Kruti Dev 010)** | DES Basic Statistics (D03–D06), Island-wise outlines (D08–D10) | The PDF text layer is ASCII. `Qlyksa dk uke` is really फसलों का नाम ("names of crops"). Every text-layer tool returns gibberish, and OCR-free pipelines never see Hindi |
| **Table ruling drawn as a raster image** | Prices 2025 (D13) | No vector lines, so pdfplumber / PyMuPDF find 0 tables |
| **Rotated (vertical) column headers** | Machinery & farmers (D07), price tables | pdfplumber returns letters in the wrong order (`d e r r IR e fs P n a` = "Transferred to PRI") |
| **Misprinted headers** | Prices 2023 (D11 p2, p12) | The year row reads `2022 2021 2020 2021`, or drops a year, while the title and the column count say 2019–2022 |
| **Same name, different place** | All | "South Andaman" is an agri zone in D01/D02, a district in DES tables, and an island in the outlines. "C/Bay", "Kamorta", "Nancowrie" are other names for zones |
| **Units hidden in footnotes** | D01/D02 | "Production of coconut in milion nuts" is printed under the table, while every other crop is in MT |
| **Prose, not tables** | Island outlines | Two columns of `Key-Value` prose are interleaved in the text layer |
| **OCR damage** | Census screenshot (D16) | Merged cells (`120 5154`), dropped cells, `Indl` read as `Indi` |

## What existing approaches already address

* **PDF table structure.** Rule/geometry extractors (pdfplumber, PyMuPDF `find_tables`, Camelot) work when ruling
  lines are vector graphics. Learned table-structure models (Table Transformer trained on PubTables-1M, Smock
  et al., CVPR 2022; TableFormer, Nassar et al., CVPR 2022) recover structure from page images. Docling
  (Auer et al., 2024, *Docling Technical Report*, arXiv:2408.09869) packages layout analysis, TableFormer and
  OCR into one converter.
* **OCR for Indic scripts.** Multilingual OCR engines (Tesseract `hin`, Surya, EasyOCR/RapidOCR) read *rendered*
  Devanagari. They need images, and they add recognition errors on clean digital PDFs.
* **Legacy font conversion.** Glyph-mapping converters for Kruti Dev / DevLys → Unicode are standard practice in
  Indian government offices (official-language, *Rajbhasha*, converters). They are character-substitution tables
  plus two reordering rules: the short-i matra is typed before its consonant, and the reph after it.
* **LLMs for semi-structured extraction.** LLMs can read and fill structured views of messy documents. Arora et
  al. (2023, *Language Models Enable Simple Systems for Generating Structured Views of Heterogeneous Data Lakes*,
  VLDB 2024) argue for using the LLM to synthesise or guide extraction while keeping bulk extraction in code, for
  cost and reliability. Table-understanding studies (Sui et al., *Table Meets LLM*, WSDM 2024; Zhang et al.,
  *TableLlama*, NAACL 2024) show that LLMs read headers and cell semantics but are sensitive to serialisation
  and table size.
* **Adapting small models.** LoRA (Hu et al., ICLR 2022) and QLoRA (Dettmers et al., NeurIPS 2023) fine-tune a
  4-bit base model with small adapters. Qwen2.5 (Qwen Team, 2024, arXiv:2412.15115) is an open-weight
  instruction family with JSON-output and multilingual (including Hindi) ability. The 3B size we use is under
  the Qwen Research License, which allows research use and fine-tuning. Most other sizes are Apache-2.0.
* **Grounding model output.** Attribution work (e.g. Gao et al., *RARR*, ACL 2023; Min et al., *FActScore*,
  EMNLP 2023) checks generated claims against evidence. We use the simplest checkable form: a verbatim evidence
  span that must contain the extracted number.

## What remains limited, for our sources

* **Research limitation:** none of the general converters we tested handles **legacy font encodings**. They trust
  the text layer, which is exactly what is wrong here. This is a known gap: font-encoding repair is outside the
  scope of layout and table-structure models.
* **Research limitation:** learned table-structure models are general but slow on CPU/MPS (88 s for one raster
  page in Docling) and still imperfect on dense 16-column numeric grids (4/6 rows correct).
* **Research limitation:** small (3B) instruction models invent schema keys and paraphrase evidence when asked
  for structured extraction (measured below). That is why we use a groundedness gate and adapters.
* **Our implementation limitation (not research):** the price agent knows the DES layout. A surprise price table
  with a different layout falls back to the LLM column mapper and is less reliable.
* **Our implementation limitation:** the island regex teacher was tuned on the same document family. Facts split
  across the two text columns are not recovered by any component.
* **Our implementation limitation:** the D18 atlas charts have no printed values, so chart digitisation is not
  implemented.

## Which approaches we selected, and why

| Trap | Selected approach | Why this, not the alternative |
|---|---|---|
| Kruti Dev | **Glyph-map decoder + bilingual label splitter** (`agri/tools/krutidev.py`), applied only to files detected as Kruti | Exact and instant on a clean text layer. Rendering + Hindi OCR would add recognition errors to text that is already correct, once decoded |
| Raster ruling | **Detect dark pixel rows/columns in the page's background image** and feed them to pdfplumber as explicit lines (`raster_rules`) | Keeps exact text-layer values (no OCR). 6/6 rows vs Docling's 4/6, in < 1 s instead of 88 s |
| Rotated headers | **Re-read only scrambled header cells with PyMuPDF clipped to the cell box** | PyMuPDF follows text direction, and pdfplumber keeps the cell geometry |
| Misprints | **Anchor on the title + printed column-number row; use the year row as a check, flag disagreements** | The title and the column count agree with each other, and the misprint is reported, not silently fixed |
| Ambiguous places | **Gazetteer with levels + aliases + level hint per source group**; LLM only picks among the top-10 fuzzy candidates, and verified answers are cached as aliases | Deterministic for known names. The model handles unseen spellings without inventing ids |
| Units | **Unit-from-title / footnote rules + `unit_raw` kept** | Never convert silently; store the printed unit and the conversion factor separately |
| Prose profiles | **LLM extraction into a fixed catalogue, groundedness gate, rule teacher fallback, QLoRA adapter** | The model is needed for unseen prose layouts. The gate and the teacher bound its errors, and the adapter targets its measured failure modes |
| OCR damage | **macOS Vision OCR + geometric re-assembly + derive a single missing cell from the row total (flagged)** | Local and accurate (0.965 mean confidence). Derivation is explicit and checkable |

## What we tested and what we learned

### Tool comparison on the four hardest cases (scored against values read from the rendered pages)

| Case | pdfplumber | PyMuPDF | Docling 2.x | **This project** |
|---|---|---|---|---|
| C1 raster-ruled price grid (D13 p1), 6 rows | 0/6 (0 tables) | 0/6 (0 tables) | 4/6 (88 s) | **6/6** (<1 s) |
| C2 rotated headers (D07 p1), 9 header strings | 2/9 | 9/9 | 9/9 | **9/9** |
| C3 Kruti Dev Hindi (D05 p1), 8 Hindi words | 0/8 | 0/8 | 0/8 | **8/8** |
| C4 screenshot table (D16), 4 rows | n/a | n/a | 4/4 (39 s) | **4/4** (<1 s) |

What we learned:
1. The encoding problem is invisible to every general tool, Docling included: 0 Devanagari characters in the output.
2. Docling's TableFormer is the only general tool that copes with raster ruling. It is slow, and it still misaligns dense rows.
3. PyMuPDF already handles rotation, so we use it narrowly, for header cells only.
4. Caveat: our tools were developed on these files, so this is evidence that the *chosen approaches* work on our sources, not a fair general benchmark.

### LLM base vs LoRA adapter (held-out documents only)

All on held-out documents (D10 islands; D02 + D06 tables); full table in [evaluation.md](evaluation.md) §2.

| Task | Base Qwen2.5-3B | + LoRA adapter |
|---|---|---|
| Island extraction F1 after groundedness gate | 0.265 | **0.935** |
| Island extraction groundedness of model items | 0.30 | **0.70** |
| Island extraction on a reworded, unseen layout (raw F1) | 0.347 | **0.724** (regex teacher: 0.607) |
| Column mapping: location + metric + period all correct | 0.027 | **0.635** |
| Column mapping: metric correct | 0.108 | **0.959** |
| Routing, model alone (manifest hidden) | 0.40 | 0.00 |

What we learned:
1. The base 3B model *invents schema keys and paraphrases evidence*. The adapter mostly fixes the format and vocabulary (catalogue adherence 0.77 → 0.91; metric ids 11% → 96%).
2. The adapter introduced *new* failure modes, which the gates contain:
   * repetition loops and illegal number literals: 39% of island replies needed the salvage parser;
   * task interference: routing, which was not in the training set, collapsed to 0%. So routing, entity resolution and narrative facts run on the base model, and the adapter is used only for the two tasks it was trained on.
3. The model's value over rules is *robustness*. On the reworded layout the regex teacher's recall falls to 0.44, while the adapter keeps 0.67.
4. Column mapping (0.635) is below our 0.8 target, so in the pipeline every model-mapped column is checked against the reference tables, and wrong ids are rejected rather than loaded.

### Other experiments

* **Rules-only ablation:** with `--no-llm` the pipeline still loads ~32k numbers from 19/20 files (D14 needs the LLM). Every loaded number is found verbatim on its cited page, and all 48 hand-checked values match. The LLM is therefore not on the critical path for the clean tables. It is needed for unseen layouts, unresolved columns, prose and routing of unknown files.
* **Cross-source consistency** (query Q7): the Agriculture Department and DES report identical paddy figures for 2023-24 but different fruit and root-crop totals (up to ~2,000 MT). That is a definitional difference between sources that the knowledge base now exposes.

## References

* Auer, C. et al. (2024). *Docling Technical Report*. arXiv:2408.09869.
* Nassar, A., Livathinos, N., Lysak, M., Staar, P. (2022). *TableFormer: Table Structure Understanding with Transformers*. CVPR.
* Smock, B., Pesala, R., Abraham, R. (2022). *PubTables-1M: Towards Comprehensive Table Extraction from Unstructured Documents*. CVPR.
* Arora, S. et al. (2023). *Language Models Enable Simple Systems for Generating Structured Views of Heterogeneous Data Lakes*. PVLDB 17(2).
* Sui, Y. et al. (2024). *Table Meets LLM: Can Large Language Models Understand Structured Table Data?* WSDM.
* Zhang, T., Yue, X., Li, Y., Sun, H. (2024). *TableLlama: Towards Open Large Generalist Models for Tables*. NAACL.
* Hu, E. J. et al. (2022). *LoRA: Low-Rank Adaptation of Large Language Models*. ICLR.
* Dettmers, T. et al. (2023). *QLoRA: Efficient Finetuning of Quantized LLMs*. NeurIPS.
* Qwen Team (2024). *Qwen2.5 Technical Report*. arXiv:2412.15115.
* Gao, L. et al. (2023). *RARR: Researching and Revising What Language Models Say, Using Language Models*. ACL.
* Min, S. et al. (2023). *FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation*. EMNLP.
* Tools: pdfplumber, PyMuPDF, Docling, Apple Vision (via ocrmac), MLX / mlx-lm, LangGraph, LangSmith, AgentEvals, RapidFuzz.
