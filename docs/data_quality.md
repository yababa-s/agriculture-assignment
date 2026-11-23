# Data quality: audit, corrections and query-time safeguards

Extraction F1 measures whether a printed cell was copied correctly. It does not catch a correctly copied
number that is stored under the wrong unit, place or crop, or a number the publisher printed wrongly. Those
errors give confident wrong answers, so Phase 3 adds three layers:

1. **Audit** (`scripts/audit_db.py`): reproducible checks over the whole knowledge base. Results are written to
   `eval/results/phase3/db_audit.json`.
2. **Corrections** (`scripts/apply_corrections.py`): rules R1–R13. Each rule was traced to a concrete defect.
   Every change is logged in the `correction` table (obs_id, rule, field, old, new, reason, time). The script is
   idempotent. Rejected rows are kept with `validation='error'` and a note, and the query tools ignore them.
3. **Query-time safeguards** (`agri/query/tools.py`, `agri/query/agent.py`):
   - unit standardisation;
   - choosing between disagreeing printed values;
   - a "sources disagree" note in the answer;
   - fallback to varieties and breakdowns.

## 1. Audit checks

| Check | What it looks for | Before | After |
|---|---|---:|---:|
| A units | a measure stored in several units | 1 | 2 (both converted at query time) |
| B jumps | a value that changes ≥10× between consecutive periods of one series | 88 | 52 |
| C bounds | a part larger than its island; any area larger than the whole UT (8,249 sq km) | 1 + 16 | 0 |
| D sums | district values that do not add up to the UT total (same document) | 60 | 1 |
| E yield | yield ≠ production / area by more than 10% | 0 | 0 |
| F conflicts | one fact printed with different values in one document | 322 | 103 (all in monthly price bulletins, handled at query time) |
| H labels | labels with undecoded Kruti Dev residue | 1,148 | 1,148 (cosmetic: Hindi half of bilingual labels; the English half is used) |

Most of the 52 remaining B jumps are real changes printed by the source; they are not extraction errors. The
fertiliser block in *Basic Statistics 2024-25* is one example: Nitrogenous falls from 137 t to 6.88 t while
Potassic rises to 3,265.5 t. We checked these against the PDF text and they are printed that way. The answers
cite the page, so a reader can check them.

## 2. Corrections (13 rules, 1,336 logged changes, 329 rows rejected)

| Rule | Defect found | Example | Rows |
|---|---|---|---:|
| R1 | item mapping | "Curry Banana" (a cooking-banana vegetable) was fuzzy-matched to *banana*; "Sax Clove" was left unmapped | 56 |
| R2 | unit stated in the label disagrees with the stored unit | cultivated area printed "(ha.)" was stored as sq km, a 100× error | 4 |
| R3 | wrong measure for the table block | seedling and pesticide rows were stored as *fertilizer consumption*, so "total fertilizer" came out as 111,271 t | 35 |
| R4 | transposed sub-tables read wrongly | rows whose label is a year or a district name | 96 |
| R5 | crop rows with no crop | category totals and misread rows | 179 |
| R6 | "Other …" / "Miscellaneous" rows stored as the category total | "Other fruits" counted as all fruits | 376 |
| R7 | a part larger than its island | Long Island cultivated area 18.18 sq km > island area (publisher decimal slip) | 1 |
| R8 | unit uncertain in the source | seed rows printed "(MT)" under a "(Kg.)" header; flagged as a warning | 23 |
| R9 | two printed rows merged into one crop | "Smooth Gourd" + "Ridge Gourd", "water spinach" + "Spinach"; "HYV" + "Paddy Traditional" kept as varieties | 96 |
| R10 | composite total stored as one crop | "Total (A+B)" (fruits including citrus) stored as citrus: Diglipur citrus 1,466 ha instead of 174 ha | 24 |
| R11 | district columns shifted | machinery tables (D04–D06): the "N & M Andaman" column was stored as Nicobar and the "Nicobar" column as the whole UT | 60 |
| R12 | district column with an unread header stored at the UT | D03 seedlings, seed and fertiliser by district | 18 |
| R13 | area impossible in sq km | the land-use table prints hectares (824,900 ha = 8,249 sq km) but was stored as sq km, so the district area read 373,600 sq km | 16 |

After corrections, field-level extraction F1 is unchanged (macro 0.999, `field_eval_v2_corrected.json`): the
rules change units, places and items, not printed values. A backup of the pre-correction database is in
`backups/`.

## 3. Query-time safeguards

- **Units.** Every value also gets `value_std` / `unit_std`: the value in the measure's standard unit, from the
  unit table's `to_base_factor`. Rankings, series and answers use the standard unit. The citation keeps the
  printed text. For example, island cultivated area printed in ha and in sq km is ranked in sq km.
- **Disagreeing printed values.** The monthly price bulletins print each month twice: as the current month, and
  again as "previous month" in the next bulletin. 103 such pairs differ. When the values for one fact differ by
  more than 5%:
  - the series keeps the candidate closest to the median of the neighbouring months;
  - a single-month lookup does the same;
  - the answer always adds a ⚠ line naming both values and their pages.

  Example: eggs in September 2025 were printed as 30.00 (p9) and 90.00 (p10), with months around them at
  84–108. The answer uses 90 and says that 30 was also printed.
- **Varieties and breakdowns.** Rice, milk, tea and edible oils are printed only by variety (Ponni / Boiled
  Common / Raw Common). Tractors and fertilisers are printed only as a breakdown. A plain question returns all
  varieties for a lookup, or the main variety's series with the others summarised. It never returns "No data".
- **Answer by measure.** A place or item name that is shared resolves to the one with data for the measure
  asked about:
  - "Car Nicobar" is a zone for crops and an island for farmers;
  - "chilli" is dry chilli for production and green chilli for prices.

## 4. Coverage battery

`data/gold/queries_battery.json` holds 97 questions. They cover:
- every measure in the database;
- every level (UT, district, zone, island);
- time forms: year, month, range, latest, relative ("last 3 years");
- synonyms and everyday wording ("how big", "how many people live on", "cattle");
- Hindi;
- provenance and source-agreement questions;
- off-topic questions.

Each question states the plan it must produce. Run it with `python scripts/query_battery.py`.

The first run passed 64 of 96. The 32 failures fell into six general causes:
1. missing everyday synonyms;
2. a measure without items being forced to name a crop;
3. a place name shared by several levels;
4. items printed only by variety;
5. "largest area" with no crop;
6. price questions phrased as rankings.

Each cause was fixed in general, and the battery now passes 97/97. The battery was used while fixing, so it is a
dev set. The held-out query test set was not used for these fixes. Its answer accuracy went from 0.80 to 0.87
because X11 (Car Nicobar Island farmers) is now resolved to the island.
