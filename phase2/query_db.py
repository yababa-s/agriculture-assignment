from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

DB = Path(os.environ.get("PHASE2_DB_PATH", str(Path(__file__).resolve().parent / "db" / "agriculture_phase2.sqlite")))

QUERIES = {
    "paddy-coconut": """SELECT commodity,metric,period,value,unit,file_name,page
      FROM v_provenance WHERE commodity IN ('Paddy','Coconut')
      ORDER BY commodity,metric,period,file_name LIMIT 20""",
    "paddy-provenance": """SELECT value_raw,value,unit,source_name,file_name,page,table_no,row_no,col_no,
      agent_id,run_id,evidence FROM v_provenance
      WHERE commodity='Paddy' AND metric='production' AND period='2024-25'""",
    "coverage": """SELECT source_group,status,COUNT(*) AS files
      FROM source_document GROUP BY source_group,status ORDER BY source_group,status""",
    "census": """SELECT metric,commodity,value,unit,file_name,page,row_no,col_no,agent_id,run_id,evidence
      FROM v_provenance WHERE metric LIKE 'operational_holdings_%' OR metric LIKE 'operated_area_%'
      ORDER BY metric""",
    "lulc-chart": """SELECT commodity,value,unit,file_name,page,agent_id,run_id,evidence
      FROM v_provenance WHERE metric='lulc_chart_visual_estimate' ORDER BY value DESC""",
    "map-legend": """SELECT d.file_name,t.page,t.fact_type,t.evidence
      FROM text_fact t JOIN source_document d USING(doc_id)
      WHERE d.doc_id IN ('P1-13','P1-15') ORDER BY d.doc_id,t.fact_id LIMIT 24""",
    "text-evidence": """SELECT d.file_name,t.page,t.fact_type,t.agent_id,t.run_id,t.evidence
      FROM text_fact t JOIN source_document d USING(doc_id)
      ORDER BY d.file_name,t.page,t.fact_id LIMIT 12""",
    "food-processing": """SELECT d.file_name,t.page,t.fact_type,t.agent_id,t.run_id,t.evidence
      FROM text_fact t JOIN source_document d USING(doc_id)
      WHERE d.file_name='food processing for sustainable growth.pdf'
      ORDER BY t.page,t.fact_id LIMIT 8""",
    "zone-table": """SELECT d.file_name,c.page,c.table_no,c.row_no,c.col_no,c.value_raw,c.agent_id,c.run_id
      FROM table_cell c JOIN source_document d USING(doc_id)
      WHERE d.file_name='42-Zone-Wise Area and Production of Crops During 2023-24.pdf'
      ORDER BY c.page,c.table_no,c.row_no,c.col_no LIMIT 24""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one of the sample queries against the local SQLite database.")
    parser.add_argument("example", choices=sorted(QUERIES))
    args = parser.parse_args()
    if not DB.exists():
        parser.error("Database missing. First run: python phase2/run_pipeline.py --fresh")
    conn = sqlite3.connect(DB)
    rows = conn.execute(QUERIES[args.example]).fetchall()
    names = [x[0] for x in conn.execute(QUERIES[args.example]).description]
    print(" | ".join(names))
    for row in rows:
        print(" | ".join("" if value is None else str(value) for value in row))
    conn.close()


if __name__ == "__main__":
    main()
