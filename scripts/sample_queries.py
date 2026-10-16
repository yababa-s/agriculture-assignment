"""Run the 10 sample queries against the knowledge base and write docs/sample_queries.md with expected results."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402

QUERIES = [
    ("Q1", "spatial", "Paddy production by agricultural zone in 2025-26, largest first",
     """SELECT l.name AS zone, o.value AS production_mt, o.document_id, o.page
FROM observation o JOIN location l ON l.location_id = o.location_id
WHERE o.metric_id='production' AND o.commodity_id='paddy' AND o.period_label='2025-26' AND l.level='agri_zone'
  AND o.value IS NOT NULL
ORDER BY o.value DESC;"""),
    ("Q2", "spatial", "Which district had the most area under arecanut in 2024-25 (DES Basic Statistics)?",
     """SELECT l.name AS district, o.value AS area_ha, o.document_id, o.page, o.table_ref
FROM observation o JOIN location l ON l.location_id = o.location_id
WHERE o.metric_id='area_cultivated' AND o.commodity_id='arecanut' AND o.period_label='2024-25'
  AND l.level='district' AND o.document_id='D06'
ORDER BY o.value DESC;"""),
    ("Q3", "temporal", "Paddy area and production for the whole UT across all reported years (every source)",
     """SELECT period_label AS year, document_id,
       MAX(CASE WHEN metric_id='area_cultivated' THEN value END) AS area_ha,
       MAX(CASE WHEN metric_id='production' THEN value END) AS production_mt
FROM observation
WHERE commodity_id='paddy' AND location_id='AN' AND metric_id IN ('area_cultivated','production')
  AND json_extract(dims,'$.item') IS NULL
GROUP BY period_label, document_id
ORDER BY period_start, document_id;"""),
    ("Q4", "temporal", "Monthly retail price of onion (Rs/kg) from Jan 2023 to Dec 2025, one value per month",
     """SELECT period_label AS month, MIN(value) AS min_reported, MAX(value) AS max_reported,
       COUNT(DISTINCT document_id) AS n_sources
FROM observation
WHERE metric_id='retail_price' AND commodity_id='onion' AND period_start BETWEEN '2023-01-01' AND '2025-12-31'
GROUP BY period_start ORDER BY period_start;"""),
    ("Q5", "provenance", "Which document, page and cell did the 2025-26 A&N coconut production figure come from?",
     """SELECT value, unit_id, value_raw, file_name, publisher, page, table_ref, row_label, col_label, agent_id, run_id
FROM v_provenance
WHERE metric_id='production' AND commodity_id='coconut' AND location_id='AN' AND period_label='2025-26';"""),
    ("Q6", "spatial", "Top 5 islands by number of farmers in 2024-25 (island-wise outline)",
     """SELECT l.name AS island, p.name AS parent, o.value AS farmers, o.page
FROM observation o JOIN location l ON l.location_id=o.location_id LEFT JOIN location p ON p.location_id=l.parent_id
WHERE o.metric_id='farmers_count' AND o.document_id='D10' AND o.value IS NOT NULL
ORDER BY o.value DESC LIMIT 5;"""),
    ("Q7", "cross-source", "Do the Agriculture Department (zone-wise) and DES (Basic Statistics) agree on 2023-24 UT totals?",
     """SELECT a.metric_id, a.commodity_id, a.value AS agri_dept_D01, b.value AS des_D05,
       ROUND(b.value - a.value, 3) AS difference
FROM observation a JOIN observation b
  ON a.metric_id=b.metric_id AND a.commodity_id=b.commodity_id AND a.location_id=b.location_id AND a.period_label=b.period_label
WHERE a.document_id='D01' AND b.document_id='D05' AND a.location_id='AN' AND a.period_label='2023-24'
  AND a.metric_id IN ('area_cultivated','production') AND a.value IS NOT NULL AND b.value IS NOT NULL
  AND json_extract(b.dims,'$.item') IS NULL
GROUP BY a.metric_id, a.commodity_id
ORDER BY ABS(b.value - a.value) DESC LIMIT 12;"""),
    ("Q8", "temporal", "Year-on-year fertilizer consumption by nutrient for the UT (MT)",
     """SELECT period_label AS year, json_extract(dims,'$.item') AS nutrient, value AS mt, document_id
FROM observation
WHERE metric_id='fertilizer_consumption' AND location_id='AN' AND json_extract(dims,'$.item') IS NOT NULL
GROUP BY period_label, nutrient HAVING document_id = MAX(document_id)
ORDER BY nutrient, period_start;"""),
    ("Q9", "census", "Agriculture Census 2015-16: holdings and area by size class (all holder types)",
     """SELECT json_extract(dims,'$.size_class') AS size_class,
       MAX(CASE WHEN metric_id='holdings_count' THEN value END) AS holdings,
       MAX(CASE WHEN metric_id='holdings_area' THEN value END) AS area_ha,
       MAX(validation) AS validation
FROM observation
WHERE document_id='D16' AND json_extract(dims,'$.holder_type')='total'
GROUP BY size_class ORDER BY MIN(obs_id);"""),
    ("Q10", "land-use + finance", "Agriculture land cover (sq km) in Andaman vs Nicobar, 2015-16 (Bhuvan LULC)",
     """SELECT json_extract(dims,'$.lulc_l2') AS lulc_class,
       MAX(CASE WHEN location_id='AN_ANDAMAN' THEN value END) AS andaman_sq_km,
       MAX(CASE WHEN location_id='AN_NIC' THEN value END) AS nicobar_sq_km
FROM observation
WHERE metric_id='lulc_area' AND json_extract(dims,'$.lulc_l1')='Agriculture'
GROUP BY lulc_class;"""),
]


def md_table(cur) -> str:
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:15]:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    if len(rows) > 15:
        out.append(f"| ... {len(rows) - 15} more rows |" + " |" * (len(cols) - 1))
    return "\n".join(out), len(rows)


def main() -> None:
    conn = sqlite3.connect(config.DB_PATH)
    parts = ["# Sample queries with expected results\n",
             f"Generated by `scripts/sample_queries.py` against `{config.DB_PATH.name}`. "
             "Re-running the script after a fresh pipeline run must reproduce these tables.\n"]
    for qid, kind, question, sql in QUERIES:
        table, n = md_table(conn.execute(sql))
        parts.append(f"## {qid} ({kind}): {question}\n\n```sql\n{sql}\n```\n\nExpected result ({n} rows):\n\n{table}\n")
        print(f"{qid}: {n} rows")
    out = config.ROOT / "docs" / "sample_queries.md"
    out.write_text("\n".join(parts))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
