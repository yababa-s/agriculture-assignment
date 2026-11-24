"""AgriAgent web app: ask questions, see answers with their source page, explore maps and evaluation results.

Run:  streamlit run app/streamlit_app.py      (or: python -m agri.cli app)
Works on any OS with only the database; the model planner is used when an LLM backend is available.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from agri import config  # noqa: E402
from agri.query.agent import QueryAgent  # noqa: E402

st.set_page_config(page_title="AgriAgent · Andaman & Nicobar", page_icon="🌾", layout="wide")


@st.cache_resource
def agent(use_llm: bool, adapter: str | None):
    llm = None
    if use_llm and config.LLM_BACKEND != "none":
        from agri.llm.client import LLM
        llm = LLM(adapter_path=adapter or config.QUERY_ADAPTER_PATH)
    return QueryAgent(config.DB_PATH, llm=llm, planner="hybrid" if llm else "rules", few_shot=False)


@st.cache_data
def sql(q: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True) as c:
        return pd.read_sql_query(q, c, params=params)


@st.cache_data
def geojson(name: str) -> dict:
    """Plotly (d3-geo) expects clockwise exterior rings; GeoJSON files store them counter-clockwise."""
    from shapely.geometry import mapping, shape
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    fc = json.loads((config.GEO_DIR / name).read_text(encoding="utf-8"))
    for f in fc["features"]:
        g = shape(f["geometry"])
        parts = [orient(p, sign=-1.0) for p in getattr(g, "geoms", [g])]
        f["geometry"] = mapping(unary_union(parts) if len(parts) == 1 else type(g)(parts))
    return fc


def frame_an(fig):
    fig.update_geos(projection_type="mercator", lonaxis_range=[91.8, 94.5], lataxis_range=[6.6, 13.9], visible=False,
                    showland=False, bgcolor="#EAF2F8")


if not config.DB_PATH.exists():
    st.error(f"Database not found at {config.DB_PATH}. Run: python scripts/fetch_artifacts.py --only database")
    st.stop()

st.title("AgriAgent · Andaman & Nicobar Islands")
st.caption("Agricultural knowledge base built by an agentic extraction pipeline. Every number links to its document, page and cell.")
with st.sidebar:
    st.header("Settings")
    use_llm = st.toggle("Use the LLM planner", value=config.LLM_BACKEND != "none",
                        disabled=config.LLM_BACKEND == "none", help="Off = rule planner (no model needed)")
    adapter = st.text_input("Adapter directory (optional)", "")
    s = sql("SELECT COUNT(*) n, COUNT(DISTINCT document_id) d FROM observation").iloc[0]
    st.metric("Observations", f"{s['n']:,}")
    st.metric("Documents with data", int(s["d"]))
    st.caption(f"DB: {config.DB_PATH.name} · backend: {config.LLM_BACKEND}")

tab_ask, tab_map, tab_explore, tab_eval = st.tabs(["Ask", "Map", "Explore", "Evaluation"])

# ------------------------------------------------------------------ Ask
with tab_ask:
    demo = json.loads((ROOT / "data" / "gold" / "demo_queries.json").read_text(encoding="utf-8"))
    pick = st.selectbox("Demo questions", ["(type your own)"] + [f"{d['id']} · {d['type']} · {d['question']}" for d in demo])
    default = "" if pick.startswith("(") else pick.split(" · ", 2)[2]
    q = st.text_input("Question (English or Hindi)", default, placeholder="Which agri zone produced the most paddy in 2025-26?")
    if q:
        ans = agent(use_llm, adapter).ask(q)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type", ans.query_type)
        c2.metric("Planner", ans.planner)
        c3.metric("Tool", ans.tool or "-")
        c4.metric("Latency", f"{ans.latency_s} s")
        st.markdown("**Answer**")
        st.code(ans.text, language=None)
        if ans.rows:
            df = pd.DataFrame(ans.rows)
            cols = [c for c in ("location", "period_label", "value", "unit_id", "document_id", "page", "table_ref",
                                "row_label", "col_label", "value_raw", "distance_km", "n_sources") if c in df]
            st.dataframe(df[cols], width="stretch", hide_index=True)
            if ans.tool == "time_series" and len(df) > 1:
                st.plotly_chart(px.line(df, x="period_label", y="value", markers=True, title=q), width="stretch")
        with st.expander("Plan, tool arguments and SQL"):
            st.json({"plan": ans.plan, "args": ans.args})
            st.code(ans.sql, language="sql")
        if ans.citations and ans.citations[0].get("obs_id"):
            if st.button("Show the source page (cell highlighted)"):
                from agri.query.provenance import render_source
                info = render_source(agent(use_llm, adapter).conn, ans.citations[0]["obs_id"])
                st.image(info["image"], caption=f"{info.get('file_name', '')} · page {info['page']} · "
                                                f"printed '{info.get('printed', '')}' (highlighted: {info['highlighted']})")

# ------------------------------------------------------------------ Map
with tab_map:
    st.subheader("District and island maps")
    st.caption("Boundaries: Census 2011 districts digitised from Survey of India maps (DataMeet). Island points: team gazetteer, "
               "checked against the district polygons.")
    mode = st.radio("Layer", ["District crop statistics", "Island indicators"], horizontal=True)
    if mode == "District crop statistics":
        crops = sql("""SELECT DISTINCT c.commodity_id, c.name FROM observation o JOIN commodity c USING(commodity_id)
                       JOIN location l USING(location_id) WHERE l.level='district' AND o.metric_id='production'
                       ORDER BY c.name""")
        crop = st.selectbox("Crop", crops["commodity_id"], index=list(crops["commodity_id"]).index("paddy"),
                            format_func=lambda c: crops.set_index("commodity_id").loc[c, "name"])
        metric = st.radio("Metric", ["production", "area_cultivated"], horizontal=True)
        df = sql("""SELECT o.location_id, l.name, o.period_label, MAX(o.value) value FROM observation o
                    JOIN location l USING(location_id) WHERE l.level='district' AND o.metric_id=? AND o.commodity_id=?
                    AND o.value IS NOT NULL AND json_extract(o.dims,'$.item') IS NULL
                    GROUP BY o.location_id, o.period_label ORDER BY MIN(o.period_start)""", (metric, crop))
        if df.empty:
            st.info("No district data for this crop.")
        else:
            fig = px.choropleth(df, geojson=geojson("an_districts.geojson"), locations="location_id",
                                featureidkey="properties.location_id", color="value", animation_frame="period_label",
                                hover_name="name", color_continuous_scale="YlOrBr",
                                range_color=(0, df["value"].max()))
            frame_an(fig)
            fig.update_layout(height=650, margin={"l": 0, "r": 0, "t": 30, "b": 0})
            st.plotly_chart(fig, width="stretch")
            st.dataframe(df.pivot(index="name", columns="period_label", values="value"), width="stretch")
    else:
        mets = {"farmers_count": "Farmers", "organic_farm_count": "Organic farms", "poultry_count": "Poultry",
                "area_under_cultivation": "Area under cultivation (sq km)", "population": "Population (2011)"}
        m = st.selectbox("Indicator", list(mets), format_func=mets.get)
        df = sql("""SELECT o.location_id, l.name, l.lat, l.lon, o.period_label, MAX(o.value) value, o.document_id,
                    MIN(o.page) page FROM observation o JOIN location l USING(location_id)
                    WHERE l.level='island' AND o.metric_id=? AND o.value IS NOT NULL
                    GROUP BY o.location_id, o.period_label ORDER BY MIN(o.period_start)""", (m,))
        fig = px.scatter_geo(df, lat="lat", lon="lon", size="value", hover_name="name", animation_frame="period_label",
                             hover_data={"value": ":,", "document_id": True, "page": True, "lat": False, "lon": False},
                             size_max=40, color_discrete_sequence=["#D55E00"])
        fig.add_trace(go.Choropleth(geojson=geojson("an_districts.geojson"), locations=["AN_NMA", "AN_SA", "AN_NIC"],
                                    featureidkey="properties.location_id", z=[1, 2, 3], showscale=False,
                                    colorscale=[[0, "#cfe3f1"], [0.5, "#f6e3c0"], [1, "#cdebdc"]], hoverinfo="skip"))
        frame_an(fig)
        fig.update_layout(height=700, margin={"l": 0, "r": 0, "t": 30, "b": 0})
        st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ Explore
with tab_explore:
    st.subheader("Browse observations with provenance")
    docs = sql("SELECT document_id, file_name FROM document ORDER BY document_id")
    d = st.selectbox("Document", docs["document_id"], format_func=lambda x: f"{x} · {docs.set_index('document_id').loc[x, 'file_name']}")
    df = sql("""SELECT obs_id, metric_id, commodity_id, location_id, period_label, value, unit_id, value_raw, page, table_ref,
                row_label, col_label, agent_id, validation FROM observation WHERE document_id=? LIMIT 5000""", (d,))
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption(f"{len(df):,} rows (first 5,000). Conflicts between sources: see the v_conflict view.")

# ------------------------------------------------------------------ Evaluation
with tab_eval:
    res = config.RESULTS_DIR / "phase3"
    f = res / f"field_eval_{config.DB_VERSION}.json"
    if f.exists():
        e = json.loads(f.read_text(encoding="utf-8"))
        st.subheader("Field-level extraction (held-out pages, hand-transcribed gold)")
        t = pd.DataFrame(e["per_agent"])[["agent", "document_id", "n_gold", "n_extracted", "precision", "recall", "f1",
                                          "provenance_accuracy"]]
        st.dataframe(t, width="stretch", hide_index=True)
        st.write(f"Macro-average F1 **{e['macro']['f1']}** over {e['n_gold_total']} gold facts.")
    rows = []
    for p in sorted(res.glob("query_eval_*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"set": e.get("set"), "configuration": e["label"], "n": e["overall"]["n"],
                     "answer accuracy": e["overall"]["answer_accuracy"], "intent accuracy": e["overall"]["intent_accuracy"],
                     "valid plans": e["overall"]["valid_plan_rate"], "median latency (s)": e["overall"]["median_latency_s"]})
    if rows:
        st.subheader("Query agent")
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
