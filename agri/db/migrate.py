"""Schema migrations. v1 -> v2 adds location.lat / lon / geo_source and fills them from data/geo/locations.csv.

Run on an existing database:  python -m agri.db.migrate [--db PATH]
init_db() calls apply_geo() too, so a fresh build is always v2.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3

from agri import config

GEO_COLUMNS = {"lat": "REAL", "lon": "REAL", "geo_source": "TEXT"}


def migrate_v2(conn: sqlite3.Connection) -> list[str]:
    have = {r[1] for r in conn.execute("PRAGMA table_info(location)")}
    added = []
    for col, typ in GEO_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE location ADD COLUMN {col} {typ}")
            added.append(col)
    return added


def apply_geo(conn: sqlite3.Connection) -> int:
    path = config.GEO_DIR / "locations.csv"
    if not path.exists():
        return 0
    n = 0
    for r in csv.DictReader(path.open()):
        cur = conn.execute("UPDATE location SET lat=?, lon=?, geo_source=? WHERE location_id=?",
                           (float(r["lat"]), float(r["lon"]), f"{r['point_type']}: {r['note'] or 'team gazetteer'}".strip(),
                            r["location_id"]))
        n += cur.rowcount
    conn.execute("INSERT OR REPLACE INTO meta_schema(key, value) VALUES ('schema_version', 'v2')")
    return n


def ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS meta_schema (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()
    conn = sqlite3.connect(a.db)
    ensure_meta(conn)
    added = migrate_v2(conn)
    n = apply_geo(conn)
    conn.commit()
    print(f"{a.db}: columns added {added or 'none (already v2)'}; {n} locations geocoded; schema_version=v2")


if __name__ == "__main__":
    main()
