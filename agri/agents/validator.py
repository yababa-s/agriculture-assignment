"""Validator agent (rules only): schema, range, unit, internal-consistency and duplicate checks.

Errors -> record goes to `rejected_record` (never silently dropped).
Warnings -> record is loaded with validation='warning' and a note.
The error rate is fed back to the orchestrator, which may retry an LLM agent.
"""
from __future__ import annotations

import json
from collections import defaultdict

RANGES = {  # (min, max) in the record's unit, generous on purpose
    "area_cultivated": (0, 900_000), "production": (0, 2_000_000), "yield": (0, 200),
    "retail_price": (0.01, 100_000), "lulc_area": (0, 10_000), "holdings_count": (0, 1_000_000),
    "holdings_area": (0, 900_000), "population": (0, 1_000_000), "farmers_count": (0, 200_000),
}
COUNT_UNITS = {"count", "persons"}


class Validator:
    agent_id = "validator_agent"

    def __init__(self, conn):
        self.conn = conn
        self.metrics = {r[0]: r[1] for r in conn.execute("SELECT metric_id, default_unit FROM metric")}
        self.locations = {r[0]: r[1] for r in conn.execute("SELECT location_id, parent_id FROM location")}
        self.commodities = {r[0] for r in conn.execute("SELECT commodity_id FROM commodity")}
        self.units = {r[0]: r[1] for r in conn.execute("SELECT unit_id, dimension FROM unit")}

    def validate(self, records: list[dict], tracer=None) -> dict:
        ok, rejected = [], []
        for rec in records:
            err = self._record_errors(rec)
            if err:
                rejected.append((rec, err))
                continue
            for w in self._record_warnings(rec):
                rec["validation"] = "warning"
                rec["validation_note"] = (rec.get("validation_note") or "") + w + "; "
            ok.append(rec)
        cross = self._cross_checks(ok)
        dups = self._duplicates(ok)
        summary = {"input": len(records), "accepted": len(ok), "rejected": len(rejected),
                   "warnings": sum(1 for r in ok if r["validation"] == "warning"), "cross_checks": cross,
                   "within_batch_duplicates": dups,
                   "error_rate": round(len(rejected) / max(1, len(records)), 4),
                   "top_errors": _top([e for _, e in rejected])}
        if tracer:
            tracer.decision("validate", "rule", summary)
        return {"accepted": ok, "rejected": rejected, "summary": summary}

    def _record_errors(self, r: dict) -> str | None:
        if r["metric_id"] not in self.metrics:
            return f"unknown metric {r['metric_id']}"
        if r["location_id"] not in self.locations:
            return f"unknown location {r['location_id']}"
        if r.get("commodity_id") and r["commodity_id"] not in self.commodities:
            return f"unknown commodity {r['commodity_id']}"
        if r.get("unit_id") and r["unit_id"] not in self.units:
            return f"unknown unit {r['unit_id']}"
        if not r.get("period_start") or not r.get("period_end") or r["period_start"] > r["period_end"]:
            return "invalid period"
        if r["value"] is None and not r.get("missing_reason"):
            return "value missing without reason"
        if r["value"] is not None:
            lo, hi = RANGES.get(r["metric_id"], (None, None))
            if r["value"] < 0 and r["metric_id"] not in ("yield",):
                return f"negative value {r['value']}"
            if hi is not None and r.get("unit_id") not in ("million_nuts",) and not (lo <= r["value"] <= hi):
                return f"value {r['value']} outside plausible range [{lo}, {hi}]"
        return None

    def _record_warnings(self, r: dict) -> list[str]:
        w = []
        if r["value"] is not None and self.units.get(r.get("unit_id")) == "count" and r["value"] != int(r["value"]):
            w.append("non-integer count")
        return w

    def _cross_checks(self, recs: list[dict]) -> dict:
        """yield = production/area; child locations sum to their parent within a table."""
        res = {"yield_checked": 0, "yield_mismatch": 0, "sum_checked": 0, "sum_mismatch": 0}
        by_key = defaultdict(dict)
        for r in recs:
            if r["metric_id"] in ("area_cultivated", "production", "yield") and r["value"] is not None:
                by_key[(r["document_id"], r["table_ref"], r["commodity_id"], r["location_id"], r["period_label"],
                        json.dumps(r["dims"], sort_keys=True))][r["metric_id"]] = r
        for k, m in by_key.items():
            if {"area_cultivated", "production", "yield"} <= m.keys() and m["area_cultivated"]["value"] > 0:
                res["yield_checked"] += 1
                y = m["production"]["value"] / m["area_cultivated"]["value"]
                if abs(y - m["yield"]["value"]) > max(0.06, 0.06 * y):
                    res["yield_mismatch"] += 1
                    m["yield"]["validation"] = "warning"
                    m["yield"]["validation_note"] = (m["yield"].get("validation_note") or "") + \
                        f"printed yield {m['yield']['value']} vs production/area {y:.2f}; "
        groups = defaultdict(list)
        for r in recs:
            if r["value"] is None or r["metric_id"] not in ("area_cultivated", "production"):
                continue
            groups[(r["document_id"], r["table_ref"], r["metric_id"], r["commodity_id"], r["period_label"],
                        json.dumps(r["dims"], sort_keys=True))].append(r)
        for _, rs in groups.items():
            by_loc = {r["location_id"]: r for r in rs}
            for parent, prec in by_loc.items():
                kids = [r for loc, r in by_loc.items() if self.locations.get(loc) == parent and loc != parent]
                if len(kids) >= 2:
                    res["sum_checked"] += 1
                    s = sum(k["value"] for k in kids)
                    if abs(s - prec["value"]) > max(0.6, 0.02 * abs(prec["value"])):
                        res["sum_mismatch"] += 1
                        prec["validation"] = "warning"
                        prec["validation_note"] = (prec.get("validation_note") or "") + \
                            f"children sum {s:.3f} != printed {prec['value']}; "
        return res

    @staticmethod
    def _duplicates(recs: list[dict]) -> int:
        from agri.db.db import dedup_key
        seen, n = set(), 0
        for r in recs:
            k = dedup_key(r)
            r["dedup_key"] = k
            if k in seen:
                n += 1
            seen.add(k)
        return n


def _top(errors: list[str], n: int = 5) -> list:
    c = defaultdict(int)
    for e in errors:
        c[e.split(" ")[0] + " " + " ".join(e.split(" ")[1:2])] += 1
    return sorted(c.items(), key=lambda x: -x[1])[:n]
