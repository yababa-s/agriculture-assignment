from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from run_pipeline import DB

QUERIES = {
    "paddy-coconut": """SELECT commodity,metric,period,value,unit,file_name,page
      FROM v_provenance WHERE commodity IN ('Paddy','Coconut')
      ORDER BY commodity,metric,period,file_name LIMIT 20""",
    "paddy-provenance": """SELECT value_raw,value,unit,source_name,file_name,page,table_no,row_no,col_no,
      agent_id,run_id,evidence FROM v_provenance
      WHERE commodity='Paddy' AND metric='production' AND period='2024-25'""",
    "coverage": """SELECT source_group,implementation_status,COUNT(*) AS files
      FROM source_document GROUP BY source_group,implementation_status ORDER BY source_group""",
    "text-evidence": """SELECT d.file_name,t.page,t.fact_type,t.agent_id,t.run_id,t.evidence
      FROM text_fact t JOIN source_document d USING(doc_id)
      ORDER BY d.file_name,t.page,t.fact_id LIMIT 12""",
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
