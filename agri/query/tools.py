"""Typed, read-only query tools over the knowledge base.

Every tool runs parameterised SQL on a read-only connection and returns rows that carry their
provenance (document, file, page, table, row label, column label, printed text, agent, run).
When several documents report the same fact, one row is chosen by a fixed rule (`pick_one`) and
the number of other sources is reported, so answers are deterministic.
"""
from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from agri import config

LEVELS = ("ut", "district", "tehsil", "agri_zone", "island", "market")

_BASE_SQL = """
SELECT o.obs_id, o.metric_id, o.commodity_id, c.name AS commodity, o.location_id, l.name AS location,
       l.level, l.lat, l.lon, o.period_label, o.period_start, o.season, o.dims, o.value, o.unit_id,
       o.value_raw, o.document_id, d.file_name, d.period_label AS doc_period, s.name AS publisher,
       o.page, o.table_ref, o.row_label, o.col_label, o.agent_id, o.run_id, o.validation
FROM observation o
JOIN location l ON l.location_id = o.location_id
JOIN document d ON d.document_id = o.document_id
JOIN source   s ON s.source_id   = d.source_id
LEFT JOIN commodity c ON c.commodity_id = o.commodity_id
WHERE o.value IS NOT NULL AND o.metric_id = :metric
  AND (:commodity IS NULL AND o.commodity_id IS NULL OR o.commodity_id = :commodity)
  AND json_extract(o.dims, '$.item') IS NULL AND json_extract(o.dims, '$.variety') IS NULL
"""


@dataclass
class ToolResult:
    tool: str
    args: dict
    sql: str
    rows: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def connect_ro(path: Path | str = config.DB_PATH) -> sqlite3.Connection:
    """Open the knowledge base read-only: query tools can never modify it."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"database not found: {p}. Run: python scripts/fetch_artifacts.py --only database")
    # read-only, so one connection may safely serve several threads (the web app answers each question on a new thread)
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _rank_key(r: dict) -> tuple:
    """Prefer: no season split, no extra dims, newest publication, then lowest obs_id (stable)."""
    return (r["season"] is not None, r["dims"] not in ("{}", '{"series": "vegetables_fruits"}', '{"series": "food_items"}'),
            -(_year(r["doc_period"]) or 0), r["obs_id"])


def _year(label: str | None) -> int | None:
    m = re.search(r"(19|20)\d\d", label or "")
    return int(m.group(0)) if m else None


def pick_one(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
    """Group rows by `key` and keep one per group (see _rank_key); adds n_sources and other_documents."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in key), []).append(r)
    out = []
    for g in groups.values():
        g.sort(key=_rank_key)
        best = dict(g[0])
        docs = sorted({x["document_id"] for x in g})
        best["n_sources"] = len(docs)
        best["other_documents"] = [d for d in docs if d != best["document_id"]]
        out.append(best)
    return out


def _fetch(conn, extra: str, params: dict, allow_items: bool = False) -> tuple[str, list[dict]]:
    sql = _BASE_SQL + extra
    if allow_items:       # measures published only as a breakdown (e.g. tractors: in department / with PRIs / private)
        sql = sql.replace("AND json_extract(o.dims, '$.item') IS NULL", "")
    return sql, [dict(r) for r in conn.execute(sql, params)]


def latest_period(conn, metric: str, commodity: str | None, level: str | None, location: str | None = None) -> str | None:
    sql = ("SELECT o.period_label FROM observation o JOIN location l ON l.location_id=o.location_id "
           "WHERE o.value IS NOT NULL AND o.metric_id=? AND o.commodity_id IS ? "
           + ("AND l.level=? " if level else "") + ("AND o.location_id=? " if location else "")
           + "ORDER BY o.period_start DESC LIMIT 1")
    params = [metric, commodity] + ([level] if level else []) + ([location] if location else [])
    r = conn.execute(sql, params).fetchone()
    return r[0] if r else None


def best_level(conn, metric: str, commodity: str | None) -> str | None:
    """The sub-UT level with most data for this metric (used when the question names no level)."""
    r = conn.execute("SELECT l.level, COUNT(*) n FROM observation o JOIN location l ON l.location_id=o.location_id "
                     "WHERE o.metric_id=? AND o.commodity_id IS ? AND l.level NOT IN ('ut','country','market') "
                     "AND o.value IS NOT NULL GROUP BY l.level ORDER BY n DESC LIMIT 1", (metric, commodity)).fetchone()
    return r[0] if r else None


# ------------------------------------------------------------------ tools
def rank_locations(conn, metric: str, commodity: str | None, period: str | None, level: str | None,
                   top_k: int = 10, order: str = "desc") -> ToolResult:
    """SPATIAL: compare locations of one level for one period, largest first (or smallest)."""
    level = level or best_level(conn, metric, commodity) or "district"
    period = period or latest_period(conn, metric, commodity, level)
    sql, rows = _fetch(conn, "AND l.level = :level AND o.period_label = :period",
                       {"metric": metric, "commodity": commodity, "level": level, "period": period})
    rows = pick_one(rows, ("location_id",))
    rows.sort(key=lambda r: r["value"], reverse=(order != "asc"))
    total = sum(r["value"] for r in rows)
    for r in rows:
        r["share_pct"] = round(100 * r["value"] / total, 1) if total else None
    return ToolResult("rank_locations", {"metric": metric, "commodity": commodity, "period": period, "level": level,
                                         "top_k": top_k, "order": order}, sql, rows[:top_k],
                      {"n_locations": len(rows), "period": period, "level": level})


def time_series(conn, metric: str, commodity: str | None, location: str, start: str | None = None,
                end: str | None = None) -> ToolResult:
    """TEMPORAL: one value per period for one location, with change and peak."""
    sql, rows = _fetch(conn, "AND o.location_id = :location AND (:start IS NULL OR o.period_start >= :start) "
                             "AND (:end IS NULL OR o.period_start <= :end)",
                       {"metric": metric, "commodity": commodity, "location": location,
                        "start": _period_start(start, first=True), "end": _period_start(end, first=False)})
    rows = pick_one(rows, ("period_label",))
    rows.sort(key=lambda r: r["period_start"])
    summary = {}
    if rows:
        first, last = rows[0], rows[-1]
        peak = max(rows, key=lambda r: r["value"])
        low = min(rows, key=lambda r: r["value"])
        summary = {"first": (first["period_label"], first["value"]), "last": (last["period_label"], last["value"]),
                   "change_pct": round(100 * (last["value"] - first["value"]) / first["value"], 1) if first["value"] else None,
                   "peak": (peak["period_label"], peak["value"]), "low": (low["period_label"], low["value"]),
                   "n_periods": len(rows), "documents": sorted({r["document_id"] for r in rows})}
    return ToolResult("time_series", {"metric": metric, "commodity": commodity, "location": location,
                                      "start": start, "end": end}, sql, rows, summary)


def trace_value(conn, metric: str, commodity: str | None, location: str, period: str | None) -> ToolResult:
    """PROVENANCE: every document, page and cell that reports this fact."""
    period = period or latest_period(conn, metric, commodity, None, location)
    params = {"metric": metric, "commodity": commodity, "location": location, "period": period}
    extra = "AND o.location_id = :location AND o.period_label = :period"
    sql, rows = _fetch(conn, extra, params)
    breakdown = False
    if not rows:
        sql, rows = _fetch(conn, extra, params, allow_items=True)
        breakdown = bool(rows)
    rows.sort(key=_rank_key) if not breakdown else rows.sort(key=lambda r: (r["document_id"], r["obs_id"]))
    return ToolResult("trace_value", {"metric": metric, "commodity": commodity, "location": location, "period": period},
                      sql, rows, {"n_sources": len({r['document_id'] for r in rows}), "period": period, "breakdown": breakdown})


def compare_sources(conn, metric: str, commodity: str | None, location: str, period: str | None = None) -> ToolResult:
    """CROSS-SOURCE: the same fact as reported by different documents, with the relative difference."""
    extra = "AND o.location_id = :location" + (" AND o.period_label = :period" if period else "")
    sql, rows = _fetch(conn, extra, {"metric": metric, "commodity": commodity, "location": location, "period": period})
    rows = pick_one(rows, ("period_label", "document_id"))
    by_period: dict[str, list[dict]] = {}
    for r in rows:
        by_period.setdefault(r["period_label"], []).append(r)
    out, n_multi, n_agree = [], 0, 0
    for p, rs in sorted(by_period.items(), key=lambda kv: kv[1][0]["period_start"]):
        vals = [r["value"] for r in rs]
        spread = round(100 * (max(vals) - min(vals)) / max(abs(min(vals)), 1e-9), 2) if len(rs) > 1 else 0.0
        if len(rs) > 1:
            n_multi += 1
            n_agree += spread <= 1.0
        for r in rs:
            r["period_spread_pct"] = spread
            out.append(r)
    return ToolResult("compare_sources", {"metric": metric, "commodity": commodity, "location": location, "period": period},
                      sql, out, {"periods_with_2plus_sources": n_multi, "periods_agreeing_within_1pct": n_agree})


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def nearby(conn, location: str, radius_km: float, metric: str | None, commodity: str | None = None,
           level: str = "island", period: str | None = None) -> ToolResult:
    """SPATIAL (distance): locations of a level within radius_km of a reference location, with a metric value."""
    ref = conn.execute("SELECT lat, lon, name FROM location WHERE location_id=?", (location,)).fetchone()
    if not ref or ref["lat"] is None:
        raise ValueError(f"{location} has no coordinates")
    cands = conn.execute("SELECT location_id, name, lat, lon FROM location WHERE level=? AND lat IS NOT NULL",
                         (level,)).fetchall()
    near = {c["location_id"]: round(haversine_km(ref["lat"], ref["lon"], c["lat"], c["lon"]), 1) for c in cands}
    near = {k: v for k, v in near.items() if v <= radius_km}
    sql = "-- haversine over location.lat/lon, then:\n" + _BASE_SQL + "AND o.location_id IN (...) AND o.period_label=:period"
    rows: list[dict] = []
    if metric and near:
        period = period or latest_period(conn, metric, commodity, level)
        params = {"metric": metric, "commodity": commodity, "period": period}
        params.update({f"n{i}": k for i, k in enumerate(near)})
        _, rows = _fetch(conn, f"AND o.location_id IN ({','.join(f':n{i}' for i in range(len(near)))}) "
                               "AND o.period_label = :period", params)
        rows = pick_one(rows, ("location_id",))
        for r in rows:
            r["distance_km"] = near[r["location_id"]]
        rows.sort(key=lambda r: -r["value"])
    else:
        rows = [{"location_id": k, "distance_km": v} for k, v in sorted(near.items(), key=lambda kv: kv[1])]
    return ToolResult("nearby", {"location": location, "radius_km": radius_km, "metric": metric, "commodity": commodity,
                                 "level": level, "period": period}, sql, rows,
                      {"reference": ref["name"], "n_within_radius": len(near)})


_SQL_GUARD = re.compile(r"^\s*(select|with)\b", re.I)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|vacuum)\b", re.I)


def safe_sql(conn, sql: str, limit: int = 200) -> ToolResult:
    """Last-resort tool: one read-only SELECT, row-limited. Also blocked by the read-only connection."""
    if not _SQL_GUARD.match(sql) or _FORBIDDEN.search(sql) or ";" in sql.strip().rstrip(";"):
        raise ValueError("only a single SELECT statement is allowed")
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM ({sql.strip().rstrip(';')}) LIMIT {int(limit)}")]
    return ToolResult("safe_sql", {"sql": sql}, sql, rows, {"n_rows": len(rows)})


_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]


def _period_start(label: str | None, first: bool) -> str | None:
    """'2019-20' -> 2019-04-01; '2023' -> 2023-01-01 / 2023-12-31; 'March 2024' -> 2024-03-01."""
    if not label:
        return None
    s = label.strip().lower()
    m = re.fullmatch(r"((?:19|20)\d\d)\s*[-–]\s*(\d\d)", s)
    if m:
        return f"{m.group(1)}-01-01" if first else f"{m.group(1)}-12-31"   # agri years start in July
    m = re.fullmatch(r"([a-z]+)\s+((?:19|20)\d\d)", s)
    if m and m.group(1) in _MONTHS:
        return f"{m.group(2)}-{_MONTHS.index(m.group(1)) + 1:02d}-01"
    m = re.fullmatch(r"(?:19|20)\d\d", s)
    if m:
        return f"{s}-01-01" if first else f"{s}-12-31"
    return None


TOOLS = {"rank_locations": rank_locations, "time_series": time_series, "trace_value": trace_value,
         "compare_sources": compare_sources, "nearby": nearby, "safe_sql": safe_sql}
