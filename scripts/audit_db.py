"""Audit the knowledge base for data errors that can produce wrong answers.

Checks (each prints counts and examples; results -> eval/results/phase3/db_audit.json):
  A. units      a metric stored in several units (must be converted before comparing); a series whose units change
  B. jumps      a value that changes by more than 10x between consecutive periods of the same series (unit/decimal slip)
  C. bounds     negative values; percentages over 100; island cultivated or forest area larger than the island
  D. sums       district values that do not add up to the UT total; zone values that do not add up to their district
  E. yield      yield that disagrees with production / area by more than 10%
  F. conflicts  the same fact printed with different values (within one document, and across documents)
  G. periods    the same fact attached to an implausible period (e.g. census figures labelled with a survey year)
  H. labels     row/column labels or dims that still contain undecoded Kruti Dev text
  I. mapping    the same printed row label mapped to different commodities in different documents
  J. places     observations attached to the combined 'Andaman' location outside the land-use tables

  python scripts/audit_db.py [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402

KRUTI = re.compile(r"[A-Za-z]*[{}\[\]~`;^|][A-Za-z]|\b(?:dk|ds|esa|vkSj|rFkk|ftyk|Qly)\b")


def q(c, sql, *p):
    return [dict(r) for r in c.execute(sql, p)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()
    c = sqlite3.connect(a.db)
    c.row_factory = sqlite3.Row
    out: dict[str, dict] = {}
    base = ("json_extract(dims,'$.item') IS NULL AND json_extract(dims,'$.variety') IS NULL AND value IS NOT NULL "
            "AND validation != 'error'")

    # A. units
    mixed = q(c, """SELECT metric_id, commodity_id, GROUP_CONCAT(DISTINCT unit_id) units, COUNT(*) n FROM observation
                     WHERE value IS NOT NULL GROUP BY metric_id, commodity_id HAVING COUNT(DISTINCT unit_id) > 1""")
    series_change = q(c, f"""SELECT metric_id, commodity_id, location_id, GROUP_CONCAT(DISTINCT unit_id) units FROM observation
                            WHERE {base} GROUP BY metric_id, commodity_id, location_id HAVING COUNT(DISTINCT unit_id) > 1""")
    out["A_units"] = {"metric_item_with_several_units": mixed, "series_with_unit_change": series_change}

    # B. jumps (in standard units)
    sys.path.insert(0, str(config.ROOT))
    from agri.query.tools import standardise
    rows = standardise(c, q(c, f"""SELECT o.*, l.level FROM observation o JOIN location l USING(location_id) WHERE {base}
                                  AND period_type != 'month' ORDER BY period_start"""))
    ser = defaultdict(dict)
    for r in rows:
        ser[(r["metric_id"], r["commodity_id"], r["location_id"])].setdefault(r["period_label"], r)
    jumps = []
    for k, d in ser.items():
        vals = list(d.values())
        for x, y in zip(vals, vals[1:]):
            a_, b_ = x["value_std"], y["value_std"]
            if a_ and b_ and a_ > 0 and b_ > 0 and max(a_ / b_, b_ / a_) >= 10 and max(a_, b_) > 5:
                jumps.append({"series": k, "from": (x["period_label"], a_, x["unit_id"], x["document_id"], x["page"]),
                              "to": (y["period_label"], b_, y["unit_id"], y["document_id"], y["page"])})
    out["B_jumps_10x"] = jumps

    # C. bounds
    neg = q(c, "SELECT obs_id, metric_id, commodity_id, location_id, period_label, value, document_id, page FROM observation WHERE value < 0")
    pct = q(c, "SELECT obs_id, metric_id, value, document_id FROM observation WHERE unit_id='percent' AND value > 100")
    isl = standardise(c, q(c, f"""SELECT o.*, l.name FROM observation o JOIN location l USING(location_id)
                               WHERE l.level='island' AND metric_id IN ('geographical_area','forest_area','area_under_cultivation') AND {base}"""))
    by = defaultdict(dict)
    for r in isl:
        by[(r["location_id"], r["period_label"])][r["metric_id"]] = r
    over = []
    for (loc, per), d in by.items():
        g = d.get("geographical_area")
        for m in ("forest_area", "area_under_cultivation"):
            if g and m in d and d[m]["value_std"] > g["value_std"] * 1.01:
                over.append({"island": loc, "period": per, "metric": m, "value_sq_km": d[m]["value_std"],
                             "printed": f"{d[m]['value_raw']} {d[m]['unit_id']}", "island_area_sq_km": g["value_std"],
                             "doc": d[m]["document_id"], "page": d[m]["page"]})
    too_big = [r for r in standardise(c, q(c, f"""SELECT o.obs_id, o.metric_id, o.location_id, o.period_label, o.value,
                                                   o.unit_id, o.document_id, o.page FROM observation o WHERE {base}
                                                   AND o.unit_id IN ('sq_km','ha')"""))
               if r["unit_id"] == "sq_km" and r["value"] > 8249 * 1.01 or r["unit_id"] == "ha" and r["value"] > 824900 * 1.01]
    out["C_bounds"] = {"negative": neg, "percent_over_100": pct, "part_larger_than_island": over,
                       "area_larger_than_ut": too_big}

    # D. sums: districts vs UT, zones vs district (same document, same metric/item/period)
    sums = []
    for parent_level, child_level in (("ut", "district"), ("district", "agri_zone")):
        rs = q(c, f"""SELECT o.metric_id, o.commodity_id, o.period_label, o.document_id, o.location_id, l.parent_id, l.level,
                             o.value, o.unit_id FROM observation o JOIN location l USING(location_id)
                      WHERE l.level IN ('{parent_level}','{child_level}') AND {base} AND o.metric_id IN ('area_cultivated','production')
                        AND o.location_id != 'AN_ANDAMAN'""")
        grp = defaultdict(lambda: {"parent": {}, "children": defaultdict(float), "n": defaultdict(int)})
        for r in rs:
            key = (r["metric_id"], r["commodity_id"], r["period_label"], r["document_id"])
            if r["level"] == parent_level:
                grp[key]["parent"][r["location_id"]] = r["value"]
            else:
                grp[key]["children"][r["parent_id"]] += r["value"]
                grp[key]["n"][r["parent_id"]] += 1
        for key, g in grp.items():
            for pid, pv in g["parent"].items():
                cv = g["children"].get(pid)
                if cv is not None and g["n"][pid] >= 2 and pv and abs(cv - pv) > 0.02 * abs(pv) and abs(cv - pv) > 1:
                    sums.append({"key": key, "parent": pid, "parent_value": pv, "children_sum": round(cv, 3),
                                 "n_children": g["n"][pid], "diff_pct": round(100 * (cv - pv) / pv, 1)})
    out["D_sums"] = sums

    # E. yield vs production / area
    yrows = q(c, """SELECT y.location_id, y.commodity_id, y.period_label, y.document_id, y.value yv, p.value pv, a.value av,
                            p.unit_id pu, a.unit_id au FROM observation y
                     JOIN observation p ON p.metric_id='production' AND p.commodity_id=y.commodity_id AND p.location_id=y.location_id
                          AND p.period_label=y.period_label AND p.document_id=y.document_id AND p.dims=y.dims
                     JOIN observation a ON a.metric_id='area_cultivated' AND a.commodity_id=y.commodity_id AND a.location_id=y.location_id
                          AND a.period_label=y.period_label AND a.document_id=y.document_id AND a.dims=y.dims
                     WHERE y.metric_id='yield' AND y.value > 0 AND a.value > 0 AND p.unit_id='mt' AND a.unit_id='ha'""")
    out["E_yield"] = [r for r in yrows if abs(r["pv"] / r["av"] - r["yv"]) > 0.1 * r["yv"] + 0.05]

    # F. conflicts
    within = q(c, """SELECT a.metric_id, a.commodity_id, a.location_id, a.period_label, a.document_id, a.page pa, a.value va,
                            b.page pb, b.value vb FROM observation a JOIN observation b
                     ON a.metric_id=b.metric_id AND a.commodity_id IS b.commodity_id AND a.location_id=b.location_id
                     AND a.period_label=b.period_label AND a.dims=b.dims AND a.document_id=b.document_id AND a.obs_id<b.obs_id
                     WHERE a.value IS NOT NULL AND b.value IS NOT NULL AND ABS(a.value-b.value) > 0.01*ABS(a.value)
                       AND a.validation != 'error' AND b.validation != 'error'""")
    across = q(c, "SELECT * FROM v_conflict")
    out["F_conflicts"] = {"within_document": within, "across_documents_count": len(across),
                          "across_documents_examples": across[:15]}

    # G. periods: island census figures should be 2011; price months should be inside the publication's coverage
    census = q(c, """SELECT metric_id, period_label, COUNT(*) n FROM observation WHERE metric_id IN ('population','households')
                     AND period_label != '2011' GROUP BY 1,2""")
    out["G_periods"] = {"census_metrics_not_2011": census}

    # H. labels with Kruti Dev residue
    lab = q(c, "SELECT DISTINCT document_id, row_label, col_label, dims FROM observation")
    resid = [r for r in lab if KRUTI.search((r["row_label"] or "") + " " + (r["col_label"] or "") + " " + (r["dims"] or ""))]
    out["H_label_residue"] = {"count": len(resid), "examples": resid[:12]}

    # I. same printed label -> different commodities
    lm = q(c, """SELECT LOWER(TRIM(row_label)) lbl, GROUP_CONCAT(DISTINCT commodity_id) items, COUNT(DISTINCT commodity_id) k
                 FROM observation WHERE commodity_id IS NOT NULL AND row_label IS NOT NULL GROUP BY 1 HAVING k > 1""")
    out["I_label_to_items"] = lm

    # J. combined location
    out["J_andaman_combined"] = q(c, "SELECT metric_id, COUNT(*) n FROM observation WHERE location_id='AN_ANDAMAN' GROUP BY 1")

    path = config.RESULTS_DIR / "phase3" / "db_audit.json"
    path.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    print("A units: metric/item with several units:", len(mixed), "| series whose unit changes:", len(series_change))
    print("B jumps ≥10x:", len(jumps))
    print("C negative:", len(neg), "| % > 100:", len(pct), "| part larger than island:", len(over),
          "| area larger than the UT:", len(too_big))
    print("D sums not adding up:", len(sums))
    print("E yield ≠ production/area:", len(out["E_yield"]))
    print("F conflicts within one document:", len(within), "| across documents:", len(across))
    print("G census metrics not labelled 2011:", census)
    print("H labels with Kruti Dev residue:", len(resid))
    print("I printed labels mapped to several items:", len(lm))
    print("J rows at the combined 'Andaman' location:", out["J_andaman_combined"])
    print("->", path)


if __name__ == "__main__":
    main()
