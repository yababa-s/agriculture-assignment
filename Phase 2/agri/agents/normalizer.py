"""Normalizer agent: resolve printed labels to canonical commodity / location / metric / unit ids.

Order of attempts (cheapest and most reliable first):
  1. exact alias match            -> decided by rule
  2. cleaned label alias match     -> decided by rule (strip numbering, '*', brackets)
  3. fuzzy match >= 90 (rapidfuzz) -> decided by rule
  4. LLM picks from top-10 fuzzy candidates -> decided by model, verified against the
     candidate list, then stored back into `alias` (origin='llm') so it is never asked twice.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from agri.llm.client import LLM

LEVEL_PREF = {
    # a hint narrows ambiguous aliases like "South Andaman" (zone vs district vs island)
    "zone": ["agri_zone", "district", "ut", "tehsil", "island"],
    "district": ["district", "ut", "agri_zone", "tehsil", "island"],
    "island": ["island", "tehsil", "district", "agri_zone", "ut"],
    "tehsil": ["tehsil", "district", "island", "agri_zone", "ut"],
}


@dataclass
class Resolution:
    entity_id: str | None
    method: str          # exact | cleaned | fuzzy | llm | unresolved
    score: float
    label: str


def norm(s: str) -> str:
    return " ".join((s or "").lower().replace("\n", " ").split())


def _clean(s: str) -> str:
    s = norm(s)
    s = re.sub(r"^\(?[a-z0-9]{1,4}[.)]\s+", "", s)          # "1 paddy", "(a) diglipur"
    s = re.sub(r"^\d+\s+", "", s)
    s = s.replace("*", "").strip(" .:-")
    return s


def _english_only(s: str) -> str:
    """Drop undecoded Kruti Dev words embedded in an English label ('b. cht seeds (kg.)' -> 'seeds (kg.)')."""
    from agri.tools.krutidev import _looks_english
    toks = [t for t in s.split() if _looks_english(t) or _looks_english(t.capitalize())]
    out = " ".join(toks)
    return _clean(out) if out else s


def _strip_brackets(s: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", s).strip()


class Normalizer:
    def __init__(self, conn: sqlite3.Connection, llm: LLM | None = None, tracer=None):
        self.conn, self.llm, self.tracer = conn, llm, tracer
        self.cache: dict[tuple, Resolution] = {}
        self.llm_calls = 0
        self._load()

    def _load(self):
        self.aliases: dict[str, dict[str, list[str]]] = {}
        for r in self.conn.execute("SELECT alias, entity_type, entity_id FROM alias"):
            self.aliases.setdefault(r["entity_type"], {}).setdefault(r["alias"], []).append(r["entity_id"])
        self.loc_level = {r["location_id"]: r["level"] for r in self.conn.execute("SELECT location_id, level FROM location")}
        self.names = {
            "commodity": {r[0]: r[1] for r in self.conn.execute("SELECT commodity_id, name FROM commodity")},
            "location": {r[0]: r[1] for r in self.conn.execute("SELECT location_id, name FROM location")},
            "metric": {r[0]: r[1] for r in self.conn.execute("SELECT metric_id, name FROM metric")},
            "unit": {r[0]: r[1] for r in self.conn.execute("SELECT unit_id, symbol FROM unit")},
        }

    def _pick(self, etype: str, ids: list[str], hint: str | None) -> str:
        if len(ids) == 1 or etype != "location" or not hint:
            return ids[0]
        prefs = LEVEL_PREF.get(hint, [])
        return sorted(ids, key=lambda i: prefs.index(self.loc_level[i]) if self.loc_level.get(i) in prefs else 99)[0]

    def resolve(self, etype: str, label: str, hint: str | None = None, use_llm: bool = True,
                context: str = "") -> Resolution:
        key = (etype, norm(label), hint)
        if key in self.cache:
            return self.cache[key]
        res = self._resolve(etype, label, hint, use_llm, context)
        self.cache[key] = res
        return res

    def _resolve(self, etype, label, hint, use_llm, context) -> Resolution:
        table = self.aliases.get(etype, {})
        n = norm(label)
        if not n:
            return Resolution(None, "unresolved", 0, label)
        if n in table:
            return Resolution(self._pick(etype, table[n], hint), "exact", 1.0, label)
        for cand in (_clean(n), _strip_brackets(_clean(n)), _english_only(_clean(n)), _strip_brackets(_english_only(_clean(n)))):
            if cand in table:
                return Resolution(self._pick(etype, table[cand], hint), "cleaned", 0.98, label)
        c = _clean(n)
        best = process.extractOne(c, table.keys(), scorer=fuzz.token_sort_ratio)
        if best and best[1] >= 90 and len(c) >= 4:
            return Resolution(self._pick(etype, table[best[0]], hint), "fuzzy", best[1] / 100, label)
        if use_llm and self.llm and self.llm.enabled and len(c) >= 3:
            return self._llm_resolve(etype, label, c, hint, context)
        return Resolution(None, "unresolved", 0, label)

    def _llm_resolve(self, etype, label, c, hint, context) -> Resolution:
        table = self.aliases[etype]
        cands = process.extract(c, table.keys(), scorer=fuzz.WRatio, limit=12)
        ids = []
        for alias, _score, _ in cands:
            for eid in table[alias]:
                if eid not in ids:
                    ids.append(eid)
        options = "\n".join(f"- {eid}: {self.names[etype].get(eid, eid)}" for eid in ids[:10])
        system = ("You resolve labels from Andaman & Nicobar agriculture statistics to canonical ids. "
                  "Answer with JSON only: {\"id\": \"<one id from the list or null>\", \"reason\": \"...\"}.")
        user = (f"Entity type: {etype}\nLabel as printed: \"{label}\"\n"
                f"{'Context: ' + context[:300] if context else ''}\nCandidate ids:\n{options}\n"
                "Choose the id that means the same thing, or null if none does.")
        if self.tracer:
            self.tracer.tool_call("llm_resolve_entity", {"etype": etype, "label": label, "candidates": ids[:10]})
        self.llm_calls += 1
        r = self.llm.json_call(system, user, max_tokens=120)
        chosen = r.parsed.get("id") if r.ok and isinstance(r.parsed, dict) else None
        valid = chosen in ids[:10]
        if self.tracer:
            self.tracer.tool_result("llm_resolve_entity", {"raw": r.text[:200], "chosen": chosen, "valid": valid}, ok=valid)
        if valid:
            from agri.db.db import add_alias
            add_alias(self.conn, etype, chosen, c, origin="llm")
            self.aliases[etype].setdefault(c, []).append(chosen)
            if self.tracer:
                self.tracer.decision("resolve_entity", "model", {"label": label, "id": chosen})
            return Resolution(chosen, "llm", 0.7, label)
        return Resolution(None, "unresolved", 0, label)
