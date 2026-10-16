"""Create (or recreate with --fresh) the knowledge-base database and seed reference tables."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri.config import DB_PATH  # noqa: E402
from agri.db.db import init_db  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="delete the existing database first")
    args = ap.parse_args()
    conn = init_db(DB_PATH, fresh=args.fresh)
    for t in ["source", "document", "agent", "location", "commodity", "unit", "metric", "alias"]:
        print(f"{t:<10} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    print(f"database: {DB_PATH}")
