"""Deterministic parsers for numbers, missing-value markers and reporting periods."""
from __future__ import annotations

import calendar
import re

_MISSING = {
    "n.a": "not_available", "n.a.": "not_available", "na": "not_available", "n/a": "not_available",
    "nil": "nil", "-": "not_applicable", "−": "not_applicable", "–": "not_applicable", "—": "not_applicable",
    "_": "not_applicable", "--": "not_applicable", "": "blank",
}
_NUM = re.compile(r"^[-−]?\d+(?:\.\d+)?$")
_LEADING_NUM = re.compile(r"^([-−]?\d[\d,]*(?:\.\d+)?)\s*(?:nos?\.?|no\.)?\s*(?:\(.*)?$", re.I)


def parse_value(raw: str | None) -> tuple[float | None, str | None]:
    """Return (value, missing_reason). Exactly one of them is None."""
    s = " ".join((raw or "").split()).strip()
    key = s.lower()
    if key in _MISSING:
        return None, _MISSING[key]
    t = s.replace(",", "").replace("−", "-")
    if _NUM.match(t):
        return float(t), None
    m = _LEADING_NUM.match(s)
    if m:
        return float(m.group(1).replace(",", "").replace("−", "-")), None
    return None, "unparseable"


def is_numeric_cell(raw: str | None) -> bool:
    v, reason = parse_value(raw)
    return v is not None or reason in ("not_available", "nil", "not_applicable")


# ---------------------------------------------------------------- periods
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9

_YEAR_RANGE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*[-–/.]\s*(\d{2}|\d{4})(?!\d)")
_MONTH_YEAR = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")[a-z]*[.,]?\s*((?:19|20)\d{2})\b", re.I)
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def parse_period(label: str, kind: str = "agri_year") -> dict | None:
    """Turn a printed period into {label, type, start, end}.

    kind decides how a 'YYYY-YY' range is anchored: agri_year = Jul-Jun (crop
    statistics), fiscal_year = Apr-Mar (budgets, census rounds use agri_year).
    """
    if not label:
        return None
    s = " ".join(str(label).split())
    m = _MONTH_YEAR.search(s)
    if m:
        mon = MONTHS[m.group(1).lower()[:3] if m.group(1).lower()[:3] in MONTHS else m.group(1).lower()]
        yr = int(m.group(2))
        last = calendar.monthrange(yr, mon)[1]
        return {"period_label": f"{calendar.month_name[mon]} {yr}", "period_type": "month",
                "period_start": f"{yr}-{mon:02d}-01", "period_end": f"{yr}-{mon:02d}-{last:02d}"}
    m = _YEAR_RANGE.search(s)
    if m:
        y1 = int(m.group(1))
        y2s = m.group(2)
        y2 = int(y2s) if len(y2s) == 4 else (y1 // 100) * 100 + int(y2s)
        if y2 < y1:
            y2 += 100
        label_out = f"{y1}-{str(y2)[-2:]}"
        if kind == "fiscal_year":
            return {"period_label": label_out, "period_type": "fiscal_year",
                    "period_start": f"{y1}-04-01", "period_end": f"{y2}-03-31"}
        ptype = "census_round" if kind == "census_round" else "agri_year"
        return {"period_label": label_out, "period_type": ptype,
                "period_start": f"{y1}-07-01", "period_end": f"{y2}-06-30"}
    m = _YEAR.search(s)
    if m:
        y = int(m.group(1))
        return {"period_label": str(y), "period_type": "calendar_year",
                "period_start": f"{y}-01-01", "period_end": f"{y}-12-31"}
    return None


def clean_label(s: str | None) -> str:
    """Collapse whitespace and strip serial numbers like '1', '(A)', 'a)' from a row label."""
    s = " ".join((s or "").split())
    s = re.sub(r"^(\(?[A-Za-z0-9]{1,3}[.)]\s+)", "", s)
    return s.strip(" :")
