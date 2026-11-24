"""Phase 3 tests: query tools and agent, provenance, geo layer, schema integrity, maintenance operations.

Tests that need the knowledge base skip themselves when it has not been fetched
(python scripts/fetch_artifacts.py --only database). No test needs an LLM.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agri import config  # noqa: E402

needs_db = pytest.mark.skipif(not config.DB_PATH.exists(), reason="knowledge base not fetched")
needs_corpus = pytest.mark.skipif(not (config.CORPUS_DIR / "Area and Production").exists(), reason="corpus not fetched")


@pytest.fixture(scope="module")
def agent():
    from agri.query.agent import QueryAgent
    return QueryAgent(config.DB_PATH, llm=None, planner="rules")


# ------------------------------------------------------------------ planner (no DB needed beyond aliases)
@needs_db
@pytest.mark.parametrize("q,intent,metric,commodity,level", [
    ("Which agri zone produced the most paddy in 2025-26?", "rank", "production", "paddy", "agri_zone"),
    ("How did paddy production in the UT change from 2019-20 to 2025-26?", "trend", "production", "paddy", None),
    ("Which source and page did the 2025-26 coconut production figure come from?", "provenance", "production", "coconut", None),
    ("Do the sources agree on paddy area in the UT?", "compare_sources", "area_cultivated", "paddy", None),
    ("Which islands within 60 km of Port Blair have the most farmers?", "nearby", "farmers_count", None, "island"),
    ("How many farmers were there on Car Nicobar Island in 2024-25?", "lookup", "farmers_count", None, None),
    ("दक्षिण अण्डमान में सुपारी का उत्पादन 2024-25", "lookup", "production", "arecanut", None),
])
def test_rule_planner(agent, q, intent, metric, commodity, level):
    p, planner, _ = agent.plan(q)
    assert planner == "rules"
    assert (p.intent, p.metric, p.commodity) == (intent, metric, commodity)
    if level:
        assert p.level == level


def test_period_parsing():
    from agri.query.agent import _find_periods
    assert _find_periods("from 2019-20 to 2025-26") == ["2019-20", "2025-26"]
    assert _find_periods("between January 2023 and March 2024") == ["January 2023", "March 2024"]
    assert _find_periods("in 2011") == ["2011"]


# ------------------------------------------------------------------ tools and answers
@needs_db
def test_rank_answer_matches_source(agent):
    a = agent.ask("Which agri zone produced the most paddy in 2025-26?")
    assert a.rows[0]["location_id"] == "ZN_DIGLIPUR" and abs(a.rows[0]["value"] - 6941.03) < 1e-6
    assert a.citations[0]["document_id"] == "D02" and a.citations[0]["page"] == 1


@needs_db
def test_provenance_answer_cites_cell(agent):
    a = agent.ask("Which source and page did the 2025-26 coconut production figure for A&N come from?")
    c = a.citations[0]
    assert (c["document_id"], c["page"], c["printed"]) == ("D02", 1, "118.616")
    assert "page 1" in a.text and "118.616" in a.text


@needs_db
def test_time_series_one_value_per_period(agent):
    a = agent.ask("Monthly retail price of onion from January 2023 to December 2025")
    periods = [r["period_label"] for r in a.rows]
    assert len(periods) == len(set(periods)) == 36


@needs_db
def test_tools_are_read_only():
    from agri.query.tools import connect_ro, safe_sql
    c = connect_ro()
    with pytest.raises(ValueError):
        safe_sql(c, "DELETE FROM observation")
    with pytest.raises(sqlite3.OperationalError):
        c.execute("DELETE FROM observation WHERE obs_id = -1")
    assert safe_sql(c, "SELECT COUNT(*) n FROM location").rows[0]["n"] > 50


@needs_db
def test_gold_query_set_passes_with_rules():
    """Regression: the 30 dev queries keep their answers (scored exactly as scripts/eval_queries.py does)."""
    from agri.query.agent import QueryAgent
    from scripts.eval_queries import check
    ag = QueryAgent(config.DB_PATH, planner="rules")
    items = json.loads((ROOT / "data" / "gold" / "queries.json").read_text())["queries"]
    wrong = []
    for it in items:
        gold = [tuple(r) for r in ag.conn.execute(it["gold_sql"]).fetchall()]
        ok, why = check(it, ag.ask(it["question"]), gold)
        if not ok:
            wrong.append((it["id"], why))
    assert not wrong, wrong


def test_demo_queries_cover_required_types():
    demo = json.loads((ROOT / "data" / "gold" / "demo_queries.json").read_text())
    types = [d["type"] for d in demo]
    assert len(demo) == 10 and types.count("spatial") >= 2 and types.count("temporal") >= 2 and "provenance" in types


# ------------------------------------------------------------------ geo + schema
def test_geo_points_inside_expected_districts():
    import csv
    rows = list(csv.DictReader((config.GEO_DIR / "locations.csv").open()))
    assert len(rows) >= 50
    assert all(r["district_check"] == "ok" and float(r["km_to_land"]) <= 5 for r in rows)


@needs_db
def test_schema_v2_and_integrity():
    c = sqlite3.connect(config.DB_PATH)
    cols = {r[1] for r in c.execute("PRAGMA table_info(location)")}
    assert {"lat", "lon", "geo_source"} <= cols
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM observation WHERE document_id IS NULL OR page IS NULL OR run_id IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM observation WHERE value IS NULL AND missing_reason IS NULL").fetchone()[0] == 0


@needs_db
def test_haversine_and_nearby():
    from agri.query.tools import connect_ro, haversine_km, nearby
    assert 175 < haversine_km(11.67, 92.74, 13.27, 92.97) < 185          # Port Blair -> Diglipur
    r = nearby(connect_ro(), "TH_PORTBLAIR", 60, "farmers_count")
    assert all(x["distance_km"] <= 60 for x in r.rows)


# ------------------------------------------------------------------ maintenance
@needs_db
def test_backup_restore_roundtrip(tmp_path):
    from agri import ops
    src = tmp_path / "kb.sqlite"
    sqlite3.connect(config.DB_PATH).backup(sqlite3.connect(src))
    gz = ops.backup(src, tmp_path / "bk")
    n_before = sqlite3.connect(src).execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    sqlite3.connect(src).execute("DELETE FROM document_chunk").connection.commit()
    ops.restore(gz, src)
    assert sqlite3.connect(src).execute("SELECT COUNT(*) FROM observation").fetchone()[0] == n_before


def test_manifest_licences_ok():
    from agri import ops
    assert ops.check_licenses() == []


def test_fetch_spec_has_checksums():
    spec = json.loads((ROOT / "artifacts.json").read_text())
    for art in spec["artifacts"].values():
        assert len(art["sha256"]) == 64 and art["file"].endswith(".zip")


@needs_db
@needs_corpus
def test_pipeline_smoke_rules_only(tmp_path):
    """One real document end to end without a model: D02 -> 2,352 records into a fresh database."""
    import subprocess
    db = tmp_path / "smoke.sqlite"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_pipeline.py"), "--docs", "D02", "--no-llm", "--db", str(db)],
                       capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM observation WHERE document_id='D02'").fetchone()[0]
    assert n > 2000
    # a corrupt, empty or missing unseen file is reported and skipped; it must not abort the batch
    bad, empty = tmp_path / "broken.pdf", tmp_path / "empty.pdf"
    bad.write_text("not a pdf")
    empty.write_bytes(b"")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_pipeline.py"), "--no-llm", "--db", str(db),
                        "--files", str(bad), str(empty), str(tmp_path / "missing.pdf")],
                       capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.count("cannot be read as a document") == 3

