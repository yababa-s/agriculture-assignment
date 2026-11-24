"""Unit tests for the deterministic core. Run: ./.venv/bin/python -m pytest -q tests"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri.tools.krutidev import krutidev_to_unicode, split_bilingual_label  # noqa: E402
from agri.tools.parsing import parse_period, parse_value  # noqa: E402


@pytest.mark.parametrize("kruti,uni", [
    ("Qlyksa dk uke", "फसलों का नाम"), ("/kku", "धान"), ("Ukkfj;y", "नारियल"), ("lqikjh", "सुपारी"),
    ("frygu", "तिलहन"), ("lfCt;k¡", "सब्जियाँ"), ("fepZ", "मिर्च"), ("nf{k.k v.Meku", "दक्षिण अण्डमान"),
    ("va- rFkk fu- }hilewg", "अं. तथा नि. द्वीपसमूह"), ("vkfFkZd ,oa lkaf[;dh funs'kky;", "आर्थिक एवं सांख्यिकी निदेशालय"),
])
def test_krutidev(kruti, uni):
    assert krutidev_to_unicode(kruti) == uni


@pytest.mark.parametrize("label,hi,en", [
    ("Ukkfj;y Coconut (M/nuts)", "नारियल", "Coconut (M/nuts)"),
    ("/kku Paddy", "धान", "Paddy"),
    ("Area (sq. km.)", "", "Area (sq. km.)"),
    ("Fertilizers-Phospatic-1.05 MT Potassic-1.85 MT", "", "Fertilizers-Phospatic-1.05 MT Potassic-1.85 MT"),
    ("mRrj v.Meku }hi North Andaman Island", "उत्तर अण्डमान द्वीप", "North Andaman Island"),
])
def test_split_bilingual(label, hi, en):
    assert split_bilingual_label(label) == (hi, en)


@pytest.mark.parametrize("raw,value,reason", [
    ("1,234.50", 1234.5, None), ("00", 0.0, None), ("N.A", None, "not_available"), ("Nil", None, "nil"),
    ("−", None, "not_applicable"), ("", None, "blank"), ("02 Nos.", 2.0, None), ("-6.21", -6.21, None),
    ("abc", None, "unparseable"),
])
def test_parse_value(raw, value, reason):
    assert parse_value(raw) == (value, reason)


def test_parse_period():
    assert parse_period("2023-24")["period_start"] == "2023-07-01"
    assert parse_period("2023-24", "fiscal_year")["period_end"] == "2024-03-31"
    assert parse_period("January, 2024")["period_label"] == "January 2024"
    assert parse_period("Dec, 2023")["period_end"] == "2023-12-31"
    assert parse_period("as on 2023- 24")["period_label"] == "2023-24"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    from agri.db.db import init_db
    return init_db(tmp_path_factory.mktemp("db") / "t.sqlite", fresh=True)


def test_normalizer_levels(conn):
    from agri.agents.normalizer import Normalizer
    n = Normalizer(conn)
    assert n.resolve("location", "C/Bay", hint="zone", use_llm=False).entity_id == "ZN_CAMPBELLBAY"
    assert n.resolve("location", "Kamorta", hint="zone", use_llm=False).entity_id == "ZN_NANCOWRY"
    assert n.resolve("location", "South Andaman", hint="zone", use_llm=False).entity_id == "ZN_SOUTHANDAMAN"
    assert n.resolve("location", "South Andaman", hint="district", use_llm=False).entity_id == "AN_SA"
    assert n.resolve("commodity", "Ladies finger", use_llm=False).entity_id == "okra"
    assert n.resolve("commodity", "Seasamum", use_llm=False).entity_id == "sesamum"
    assert n.resolve("metric", "Prodn.", use_llm=False).entity_id == "production"


def test_validator(conn):
    from agri.agents.validator import Validator
    v = Validator(conn)
    base = {"metric_id": "area_cultivated", "commodity_id": "paddy", "location_id": "AN", "period_label": "2023-24",
            "period_type": "agri_year", "period_start": "2023-07-01", "period_end": "2024-06-30", "dims": {}, "value": 10.0,
            "unit_id": "ha", "value_raw": "10", "missing_reason": None, "document_id": "D01", "page": 1, "table_ref": "t",
            "row_label": "Paddy", "col_label": "x", "validation": "ok", "validation_note": None}
    bad = dict(base, value=-1.0)
    unknown = dict(base, location_id="NOWHERE")
    out = v.validate([base, bad, unknown])
    assert out["summary"]["accepted"] == 1 and out["summary"]["rejected"] == 2
