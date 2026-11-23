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
WHERE o.value IS NOT NULL AND o.validation != 'error' AND o.metric_id = :metric
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


CONFLICT_PCT = 5.0     # printed values of one fact further apart than this are reported as a disagreement


def pick_one(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
    """Group rows by `key` and keep one per group (see _rank_key); adds n_sources and other_documents.
    When the printed values in a group disagree by more than CONFLICT_PCT, the other values are kept in
    `alternatives` so a caller can choose by context (time_series) and the answer can say the sources disagree."""
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
        alts, seen = [], {round(best["value_std"], 6)}
        for x in g[1:]:
            v = x["value_std"]
            if round(v, 6) not in seen and abs(v - best["value_std"]) > CONFLICT_PCT / 100 * max(abs(best["value_std"]), 1e-9):
                seen.add(round(v, 6))
                alts.append(dict(x))
        best["alternatives"] = alts
        out.append(best)
    return out


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def resolve_by_neighbours(rows: list[dict], window: int = 2) -> int:
    """For a period whose sources disagree, keep the candidate closest to the median of the neighbouring periods
    (a printing slip such as eggs '30.00' between months of 84-96 loses to the reprint '90.00'). Returns the number
    of periods where the choice changed. The rejected values stay in `alternatives` for the answer to mention."""
    changed = 0
    for i, r in enumerate(rows):
        if not r.get("alternatives"):
            continue
        nb = [x["value_std"] for j, x in enumerate(rows) if j != i and abs(j - i) <= window and not x.get("alternatives")]
        if len(nb) < 2:
            continue
        med = _median(nb)
        cands = [r] + r["alternatives"]
        best = min(cands, key=lambda x: abs(math.log(max(x["value_std"], 1e-9) / max(med, 1e-9))))
        if best is not r:
            new = dict(best)
            new.update({k: r[k] for k in ("n_sources", "other_documents")})
            new["alternatives"] = [c for c in cands if c is not best]
            new["chosen_by"] = f"closest to the neighbouring periods, median {med:.4g}"
            rows[i] = new
            changed += 1
    return changed


_UNITS: dict[int, tuple[dict, dict]] = {}


def _unit_tables(conn) -> tuple[dict, dict]:
    key = id(conn)
    if key not in _UNITS:
        units = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT unit_id, base_unit_id, to_base_factor FROM unit")}
        default = {r[0]: r[1] for r in conn.execute("SELECT metric_id, default_unit FROM metric")}
        _UNITS[key] = (units, default)
    return _UNITS[key]


def standardise(conn, rows: list[dict]) -> list[dict]:
    """Add value_std / unit_std: the value in the metric's standard unit (e.g. island cultivated area printed in ha
    becomes sq km), so rankings and series never mix units. value / value_raw / unit_id stay as printed."""
    units, default = _unit_tables(conn)
    for r in rows:
        u, d = r.get("unit_id"), default.get(r.get("metric_id"))
        r["value_std"], r["unit_std"] = r.get("value"), u
        if u and d and u != d and u in units and d in units and units[u][0] == units[d][0] and r.get("value") is not None:
            r["value_std"] = r["value"] * units[u][1] / units[d][1]
            r["unit_std"] = d
    return rows


def _fetch(conn, extra: str, params: dict, allow_items: bool = False, allow_variety: bool = False) -> tuple[str, list[dict]]:
    sql = _BASE_SQL + extra
    if allow_items:       # measures published only as a breakdown (e.g. tractors: in department / with PRIs / private)
        sql = sql.replace("AND json_extract(o.dims, '$.item') IS NULL", "")
    if allow_variety:     # items printed only by variety (rice: Ponni / Boiled Common / Raw Common; paddy: HYV / traditional)
        sql = sql.replace("AND json_extract(o.dims, '$.variety') IS NULL", "")
    return sql, standardise(conn, [dict(r) for r in conn.execute(sql, params)])


def part_of(r: dict, kind: str) -> str:
    """The printed variety or breakdown item of a row (English part of a bilingual label)."""
    import json as _json
    raw = str(_json.loads(r.get("dims") or "{}").get(kind, "")).strip(" -")
    from agri.tools.krutidev import split_bilingual_label
    return (split_bilingual_label(raw)[1] or raw).strip(" -") or "(unlabelled)"


def _fetch_parts(conn, extra: str, params: dict) -> tuple[str, list[dict], str | None]:
    """Rows for the plain fact; if there are none, the varieties; if none, the breakdown items.
    Returns (sql, rows, part) with part None | 'variety' | 'item'; every row then carries r['part']."""
    sql, rows = _fetch(conn, extra, params)
    if rows:
        return sql, rows, None
    for kind, kw in (("variety", {"allow_variety": True}), ("item", {"allow_items": True})):
        sql, rows = _fetch(conn, extra, params, **kw)
        if rows:
            for r in rows:
                r["part"] = part_of(r, kind)
            return sql, rows, kind
    return sql, [], None


def latest_period(conn, metric: str, commodity: str | None, level: str | None, location: str | None = None) -> str | None:
    sql = ("SELECT o.period_label FROM observation o JOIN location l ON l.location_id=o.location_id "
           "WHERE o.value IS NOT NULL AND o.validation != 'error' AND o.metric_id=? AND o.commodity_id IS ? "
           + ("AND l.level=? " if level else "") + ("AND o.location_id=? " if location else "")
           + "ORDER BY o.period_start DESC LIMIT 1")
    params = [metric, commodity] + ([level] if level else []) + ([location] if location else [])
    r = conn.execute(sql, params).fetchone()
    return r[0] if r else None


def best_level(conn, metric: str, commodity: str | None) -> str | None:
    """The sub-UT level with most data for this metric (used when the question names no level)."""
    r = conn.execute("SELECT l.level, COUNT(*) n FROM observation o JOIN location l ON l.location_id=o.location_id "
                     "WHERE o.metric_id=? AND o.commodity_id IS ? AND l.level NOT IN ('ut','country','market') "
                     "AND o.value IS NOT NULL AND o.validation != 'error' GROUP BY l.level ORDER BY n DESC LIMIT 1", (metric, commodity)).fetchone()
    return r[0] if r else None


# ------------------------------------------------------------------ tools
def rank_locations(conn, metric: str, commodity: str | None, period: str | None, level: str | None,
                   top_k: int = 10, order: str = "desc") -> ToolResult:
    """SPATIAL: compare locations of one level for one period, largest first (or smallest)."""
    level = level or best_level(conn, metric, commodity) or "district"
    period = period or latest_period(conn, metric, commodity, level)
    sql, rows, part = _fetch_parts(conn, "AND l.level = :level AND o.period_label = :period",
                                   {"metric": metric, "commodity": commodity, "level": level, "period": period})
    parts_seen = []
    if part:                     # rank one variety / item at a time: the one reported for most places
        cnt: dict[str, set] = {}
        for r in rows:
            cnt.setdefault(r["part"], set()).add(r["location_id"])
        parts_seen = sorted(cnt, key=lambda k: -len(cnt[k]))
        rows = [r for r in rows if r["part"] == parts_seen[0]]
    rows = pick_one(rows, ("location_id",))
    rows.sort(key=lambda r: r["value_std"], reverse=(order != "asc"))
    total = sum(r["value_std"] for r in rows)
    for r in rows:
        r["share_pct"] = round(100 * r["value_std"] / total, 1) if total else None
    return ToolResult("rank_locations", {"metric": metric, "commodity": commodity, "period": period, "level": level,
                                         "top_k": top_k, "order": order}, sql, rows[:top_k],
                      {"n_locations": len(rows), "period": period, "level": level, "part_kind": part,
                       "part": parts_seen[0] if parts_seen else None, "other_parts": parts_seen[1:]})


def time_series(conn, metric: str, commodity: str | None, location: str, start: str | None = None,
                end: str | None = None) -> ToolResult:
    """TEMPORAL: one value per period for one location, with change and peak."""
    sql, rows, part = _fetch_parts(conn, "AND o.location_id = :location AND (:start IS NULL OR o.period_start >= :start) "
                                         "AND (:end IS NULL OR o.period_start <= :end)",
                                   {"metric": metric, "commodity": commodity, "location": location,
                                    "start": _period_start(start, first=True), "end": _period_start(end, first=False)})
    parts: dict[str, list[dict]] = {}
    if part:                      # one series per variety / breakdown item; the main one is the longest
        for r in rows:
            parts.setdefault(r["part"], []).append(r)
        for k in parts:
            parts[k] = pick_one(parts[k], ("period_label",))
            parts[k].sort(key=lambda r: r["period_start"])
            resolve_by_neighbours(parts[k])
        main = max(parts, key=lambda k: (len(parts[k]), -list(parts).index(k)))
        rows = parts[main]
    else:
        rows = pick_one(rows, ("period_label",))
        rows.sort(key=lambda r: r["period_start"])
    n_fixed = resolve_by_neighbours(rows)
    summary = {}
    if rows:
        first, last = rows[0], rows[-1]
        peak = max(rows, key=lambda r: r["value_std"])
        low = min(rows, key=lambda r: r["value_std"])
        summary = {"first": (first["period_label"], first["value_std"]), "last": (last["period_label"], last["value_std"]),
                   "change_pct": round(100 * (last["value_std"] - first["value_std"]) / first["value_std"], 1)
                   if first["value_std"] else None,
                   "peak": (peak["period_label"], peak["value_std"]), "low": (low["period_label"], low["value_std"]),
                   "n_periods": len(rows), "documents": sorted({r["document_id"] for r in rows}),
                   "n_conflicts": sum(bool(r.get("alternatives")) for r in rows), "n_resolved_by_neighbours": n_fixed,
                   "part_kind": part, "part": rows[0].get("part"),
                   "other_parts": {k: {"first": (v[0]["period_label"], v[0]["value_std"]),
                                       "last": (v[-1]["period_label"], v[-1]["value_std"]), "n": len(v),
                                       "unit": v[0].get("unit_std")}
                                   for k, v in parts.items() if v and k != rows[0].get("part")}}
    return ToolResult("time_series", {"metric": metric, "commodity": commodity, "location": location,
                                      "start": start, "end": end}, sql, rows, summary)


def trace_value(conn, metric: str, commodity: str | None, location: str, period: str | None) -> ToolResult:
    """PROVENANCE: every document, page and cell that reports this fact."""
    period = period or latest_period(conn, metric, commodity, None, location)
    params = {"metric": metric, "commodity": commodity, "location": location, "period": period}
    extra = "AND o.location_id = :location AND o.period_label = :period"
    sql, rows, part = _fetch_parts(conn, extra, params)
    breakdown = part is not None
    rows.sort(key=_rank_key) if not breakdown else rows.sort(key=lambda r: (r["document_id"], r["obs_id"]))
    chosen_by = None
    vals = [r["value_std"] for r in rows]
    if not breakdown and len(rows) > 1 and max(vals) - min(vals) > CONFLICT_PCT / 100 * max(abs(v) for v in vals) \
            and rows[0].get("period_start") and re.match(r"^[A-Z][a-z]+ \d{4}$", period or ""):
        # monthly value printed differently on two pages: keep the one consistent with the months around it
        ser = time_series(conn, metric, commodity, location)
        hit = next((r for r in ser.rows if r["period_label"] == period), None)
        if hit and hit.get("chosen_by"):
            rows.sort(key=lambda r: abs(r["value_std"] - hit["value_std"]))
            chosen_by = hit["chosen_by"]
    return ToolResult("trace_value", {"metric": metric, "commodity": commodity, "location": location, "period": period},
                      sql, rows, {"n_sources": len({r['document_id'] for r in rows}), "period": period,
                                  "breakdown": breakdown, "part_kind": part, "chosen_by": chosen_by})


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
        rows.sort(key=lambda r: -r["value_std"])
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
