"""Make every figure and animation used in the report, poster and slides, from the knowledge base.

  python scripts/make_figures.py            # all figures -> figures/, animations -> figures/anim/
  python scripts/make_figures.py --only maps

Maps use the district and island polygons in data/geo/ (Census 2011 district boundaries digitised from
Survey of India maps, republished by DataMeet) and the India outline built from the same Survey of India
based data, so the inset shows India's official boundary. Every map carries its data source.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import animation  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from agri import config  # noqa: E402

FIG = config.FIGURES_DIR
ANIM = FIG / "anim"
GEO = config.GEO_DIR
SRC_NOTE = "Boundaries: Census 2011 districts digitised from Survey of India maps (DataMeet). Data: AgriAgent KB v2."
# palette (colour-blind safe, Okabe-Ito based)
C = {"NMA": "#0072B2", "SA": "#E69F00", "NIC": "#009E73", "sea": "#EAF2F8", "land": "#F4F1EA", "edge": "#7A7A7A",
     "ink": "#222222", "muted": "#6B6B6B", "accent": "#D55E00", "paddy": "#C9A227", "areca": "#2E7D32"}
DIST = {"AN_NMA": ("North & Middle Andaman", C["NMA"]), "AN_SA": ("South Andaman", C["SA"]), "AN_NIC": ("Nicobar", C["NIC"])}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 13, "savefig.dpi": 300, "figure.dpi": 100})


def db() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def q(sql: str, *p) -> list[sqlite3.Row]:
    return db().execute(sql, p).fetchall()


def load_geo(name: str) -> list[tuple[dict, object]]:
    fc = json.loads((GEO / name).read_text(encoding="utf-8"))
    return [(f["properties"], shape(f["geometry"])) for f in fc["features"]]


def draw_geom(ax, geom, **kw):
    polys = getattr(geom, "geoms", [geom])
    patches = [MplPolygon(np.asarray(p.exterior.coords), closed=True) for p in polys]
    ax.add_collection(PatchCollection(patches, **kw))


def base_map(ax, fill_by_district: dict[str, str] | None = None, alpha: float = 1.0):
    ax.set_facecolor(C["sea"])
    for props, g in load_geo("an_districts.geojson"):
        col = (fill_by_district or {}).get(props["location_id"], C["land"])
        draw_geom(ax, g, facecolor=col, edgecolor=C["edge"], linewidth=0.4, alpha=alpha)
    ax.set_xlim(91.9, 94.4)
    ax.set_ylim(6.6, 13.85)
    ax.set_aspect("equal")
    ax.set_xticks([92, 93, 94])
    ax.set_yticks([7, 8, 9, 10, 11, 12, 13])
    ax.set_xticklabels(["92°E", "93°E", "94°E"], fontsize=8, color=C["muted"])
    ax.set_yticklabels([f"{v}°N" for v in range(7, 14)], fontsize=8, color=C["muted"])
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)


def north_arrow_and_scale(ax):
    ax.annotate("N", xy=(94.2, 13.6), xytext=(94.2, 13.2), ha="center", fontsize=11, fontweight="bold",
                arrowprops={"arrowstyle": "-|>", "color": C["ink"], "lw": 1.5})
    # 100 km at ~10°N: 100 / (111.32 * cos(10°)) degrees of longitude
    w = 100 / (111.32 * np.cos(np.radians(10)))
    ax.plot([92.0, 92.0 + w], [6.85, 6.85], color=C["ink"], lw=3, solid_capstyle="butt")
    ax.text(92.0 + w / 2, 6.95, "100 km", ha="center", fontsize=8)


def india_inset(fig, rect=(0.62, 0.06, 0.3, 0.3)):
    ax = fig.add_axes(rect)
    for _, g in load_geo("india_outline.geojson"):
        draw_geom(ax, g, facecolor="#DDDDDD", edgecolor="#888888", linewidth=0.3)
    ax.add_patch(plt.Rectangle((91.9, 6.6), 2.5, 7.3, fill=False, edgecolor=C["accent"], lw=1.4))
    ax.set_xlim(67, 98)
    ax.set_ylim(6, 37.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(82.5, 6.3, "India (Survey of India boundary)", ha="center", fontsize=6.5, color=C["muted"])
    return ax


def loc_xy() -> dict[str, tuple[float, float]]:
    return {r["location_id"]: (r["lon"], r["lat"]) for r in q("SELECT location_id, lat, lon FROM location WHERE lat IS NOT NULL")}


def save(fig, name: str, note: str | None = SRC_NOTE):
    if note:
        fig.text(0.01, 0.005, note, fontsize=6.5, color=C["muted"], ha="left", va="bottom")
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  figures/{name}.png")


# ------------------------------------------------------------------ data helpers
def series_by_location(metric: str, commodity: str | None, level: str) -> dict[str, dict[str, float]]:
    rows = q("""SELECT o.location_id, o.period_label, o.period_start, MAX(o.value) v FROM observation o
                JOIN location l ON l.location_id=o.location_id
                WHERE o.metric_id=? AND o.commodity_id IS ? AND l.level=? AND o.value IS NOT NULL
                  AND json_extract(o.dims,'$.item') IS NULL
                GROUP BY o.location_id, o.period_label ORDER BY o.period_start""", metric, commodity, level)
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["location_id"], {})[r["period_label"]] = r["v"]
    return out


def ut_series(metric: str, commodity: str) -> list[tuple[str, float]]:
    rows = q("""SELECT period_label, MAX(value) v FROM observation WHERE metric_id=? AND commodity_id=? AND location_id='AN'
                AND value IS NOT NULL AND json_extract(dims,'$.item') IS NULL GROUP BY period_label ORDER BY MIN(period_start)""",
             metric, commodity)
    return [(r["period_label"], r["v"]) for r in rows]


# ------------------------------------------------------------------ figures
def fig_study_area():
    fig, ax = plt.subplots(figsize=(6.2, 9))
    base_map(ax, {k: v[1] for k, v in DIST.items()}, alpha=0.55)
    xy = loc_xy()
    isl = [r["location_id"] for r in q("SELECT location_id FROM location WHERE level='island' AND lat IS NOT NULL")]
    ax.scatter([xy[i][0] for i in isl], [xy[i][1] for i in isl], s=10, color=C["ink"], zorder=3, label="Island profile (31)")
    zones = [r["location_id"] for r in q("SELECT location_id FROM location WHERE level='agri_zone'")]
    ax.scatter([xy[z][0] for z in zones], [xy[z][1] for z in zones], s=70, marker="^", color=C["accent"],
               edgecolor="white", zorder=4, label="Agriculture zone HQ (8)")
    ax.scatter(*xy["MKT_AN"], s=120, marker="*", color="#CC79A7", edgecolor="white", zorder=5, label="Port Blair retail market")
    for lid, (name, col) in DIST.items():
        lon, lat = {"AN_NMA": (93.35, 12.75), "AN_SA": (93.3, 11.0), "AN_NIC": (92.2, 8.2)}[lid]
        n = q("SELECT COUNT(*) n FROM observation o JOIN location l ON l.location_id=o.location_id "
              "WHERE l.location_id=? OR l.parent_id=? OR l.parent_id IN (SELECT location_id FROM location WHERE parent_id=?)",
              lid, lid, lid)[0]["n"]
        ax.text(lon, lat, f"{name}\n{n:,} records", fontsize=9, fontweight="bold", color=col, ha="center")
    north_arrow_and_scale(ax)
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    ax.set_title("Study area: Andaman & Nicobar Islands\n3 districts · 8 agri zones · 31 islands", loc="left")
    india_inset(fig, (0.55, 0.12, 0.38, 0.28))
    save(fig, "fig1_study_area")


def fig_paddy_hero():
    """Poster hero: district map of paddy change + zone bubbles + sparklines + arecanut contrast."""
    paddy = series_by_location("production", "paddy", "district")
    areca = series_by_location("area_cultivated", "arecanut", "district")
    zones = series_by_location("production", "paddy", "agri_zone")
    y0, y1 = "2021-22", "2025-26"
    change = {d: 100 * (paddy[d][y1] - paddy[d][y0]) / paddy[d][y0] for d in paddy if y0 in paddy[d] and y1 in paddy[d]}
    fig = plt.figure(figsize=(13, 8.5))
    ax = fig.add_axes([0.0, 0.1, 0.36, 0.78])
    cmap = plt.get_cmap("RdYlGn")
    fills = {d: cmap(0.5 + max(-0.5, min(0.5, v / 100))) for d, v in change.items()}
    base_map(ax, fills, alpha=0.9)
    xy = loc_xy()
    for z, s in zones.items():
        if s.get(y1):
            ax.scatter(*xy[z], s=40 + s[y1] / 12, color=C["paddy"], edgecolor=C["ink"], linewidth=0.6, alpha=0.85, zorder=4)
            zname = q("SELECT name FROM location WHERE location_id=?", z)[0]["name"].replace(" (agri zone)", "")
            ax.text(xy[z][0] + 0.14, xy[z][1], f"{zname}\n{s[y1]:,.0f} t", fontsize=8, va="center")
    north_arrow_and_scale(ax)
    ax.set_title("Paddy production change by district, 2021-22 → 2025-26\n(bubbles: zone production 2025-26, tonnes)",
                 loc="left", fontsize=12)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-100, 100))
    cb = fig.colorbar(sm, cax=fig.add_axes([0.06, 0.06, 0.24, 0.015]), orientation="horizontal")
    cb.set_label("% change in district paddy production", fontsize=9)
    # right column: one row of sparklines per district
    years = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    for i, (d, (name, col)) in enumerate(DIST.items()):
        a1 = fig.add_axes([0.45, 0.64 - i * 0.27, 0.23, 0.18])
        a2 = fig.add_axes([0.75, 0.64 - i * 0.27, 0.23, 0.18])
        pv = [paddy.get(d, {}).get(y) for y in years]
        av = [areca.get(d, {}).get(y) for y in years]
        a1.plot(range(5), pv, "-o", color=C["paddy"], lw=2.2, ms=4)
        a2.plot(range(5), av, "-o", color=C["areca"], lw=2.2, ms=4)
        for a, vals, unit in ((a1, pv, "t"), (a2, av, "ha")):
            a.set_xticks(range(5))
            a.set_xticklabels([y[2:4] + "-" + y[-2:] for y in years], fontsize=7)
            a.tick_params(axis="y", labelsize=7)
            if vals[0] and vals[-1]:
                pct = 100 * (vals[-1] - vals[0]) / vals[0]
                a.set_title(f"{pct:+.0f}%  ({vals[0]:,.0f} → {vals[-1]:,.0f} {unit})", fontsize=9, loc="left",
                            color=C["accent"] if pct < 0 else C["areca"])
        a1.set_ylabel(name, fontsize=9, fontweight="bold", color=col)
    fig.text(0.45, 0.88, "Paddy production (t)", fontsize=11, fontweight="bold", color=C["paddy"])
    fig.text(0.75, 0.88, "Arecanut area (ha)", fontsize=11, fontweight="bold", color=C["areca"])
    fig.suptitle("Where paddy is shrinking, arecanut is growing: North & Middle Andaman", x=0.02, ha="left",
                 fontsize=15, fontweight="bold")
    save(fig, "fig4_paddy_vs_arecanut_map", SRC_NOTE + " Paddy: DES Basic Statistics D03–D06 and Agri Dept D02; "
         "arecanut: same sources. n = 3 districts × 5 years.")


def fig_ut_trends():
    fig, ax = plt.subplots(figsize=(8, 4.2))
    p = ut_series("production", "paddy")
    ar = ut_series("area_cultivated", "arecanut")
    ax.plot([x for x, _ in p], [v for _, v in p], "-o", color=C["paddy"], lw=2.5, label="Paddy production (t)")
    ax2 = ax.twinx()
    ax2.plot([x for x, _ in ar], [v for _, v in ar], "-s", color=C["areca"], lw=2.5, label="Arecanut area (ha)")
    ax.set_ylabel("Paddy production (t)", color=C["paddy"])
    ax2.set_ylabel("Arecanut area (ha)", color=C["areca"])
    ax2.spines["right"].set_visible(True)
    ax.set_title("A&N Islands: paddy output down 46% since 2019-20 while arecanut area expands", loc="left", fontsize=11)
    ax.tick_params(axis="x", rotation=30)
    fig.legend(loc="upper right", bbox_to_anchor=(0.88, 0.85), fontsize=9)
    save(fig, "fig5_ut_paddy_arecanut_trend", "Data: AgriAgent KB v2 (DES Basic Statistics D03–D06, Agri Dept D01–D02); "
         "one value per year, n = 7 years.")


def price_matrix(commodities: list[str]):
    rows = q(f"""SELECT commodity_id, period_label, period_start, MAX(value) v FROM observation
                WHERE metric_id='retail_price' AND commodity_id IN ({','.join('?' * len(commodities))})
                  AND period_type='month' AND period_start BETWEEN '2023-01-01' AND '2025-12-31'
                  AND json_extract(dims,'$.variety') IS NULL
                GROUP BY commodity_id, period_start ORDER BY period_start""", *commodities)
    months = sorted({r["period_start"] for r in rows})
    M = np.full((len(commodities), len(months)), np.nan)
    for r in rows:
        M[commodities.index(r["commodity_id"]), months.index(r["period_start"])] = r["v"]
    return M, months


PRICE_ITEMS = ["onion", "tomato", "potato", "brinjal", "okra", "green_chilli", "ginger", "garlic", "cabbage", "eggs"]


def fig_price_heatmap():
    M, months = price_matrix(PRICE_ITEMS)
    idx = M / np.nanmean(M, axis=1, keepdims=True)  # price relative to the item's own 3-year mean
    fig, ax = plt.subplots(figsize=(12, 4.6))
    im = ax.imshow(idx, aspect="auto", cmap="RdBu_r", vmin=0.4, vmax=1.6)
    ax.set_yticks(range(len(PRICE_ITEMS)))
    ax.set_yticklabels([i.replace("_", " ").title() for i in PRICE_ITEMS])
    ax.set_xticks(range(0, len(months), 3))
    ax.set_xticklabels([m[:7] for m in months[::3]], rotation=45, fontsize=8)
    cb = fig.colorbar(im, ax=ax, fraction=0.025)
    cb.set_label("price ÷ item's 2023–25 mean")
    o = PRICE_ITEMS.index("onion")
    j = int(np.nanargmax(M[o]))
    ax.add_patch(plt.Rectangle((j - 0.5, o - 0.5), 1, 1, fill=False, edgecolor="black", lw=2))
    ax.annotate(f"Onion peak {M[o, j]:.1f} INR/kg ({months[j][:7]})", (j, o), (j - 14, o - 1.3), fontsize=9,
                arrowprops={"arrowstyle": "->"})
    ax.set_title("Port Blair retail prices, Jan 2023 – Dec 2025: vegetables spike in the monsoon and in Nov–Dec",
                 loc="left", fontsize=12)
    save(fig, "fig6_price_calendar", "Data: DES Comparative Statement of Prices D11–D13 (36 months × 10 items, n = 360 cells).")


def fig_islands():
    xy = loc_xy()
    f = {r["location_id"]: r["v"] for r in q("""SELECT o.location_id, MAX(o.value) v FROM observation o JOIN location l
         ON l.location_id=o.location_id WHERE o.metric_id='farmers_count' AND l.level='island' AND o.period_label='2024-25'
         AND o.value IS NOT NULL GROUP BY o.location_id""")}
    cult = {r["location_id"]: r["v"] for r in q("""SELECT o.location_id, MAX(o.value) v FROM observation o JOIN location l
         ON l.location_id=o.location_id WHERE o.metric_id='area_under_cultivation' AND l.level='island' AND o.period_label='2024-25'
         AND o.unit_id='sq_km' GROUP BY o.location_id""")}
    fig, ax = plt.subplots(figsize=(6.5, 9))
    base_map(ax)
    for props, g in load_geo("an_islands.geojson"):
        lid = props["location_id"]
        if lid in f:
            draw_geom(ax, g, facecolor=plt.cm.YlGn(0.25 + 0.75 * min(1, f[lid] / 9000)), edgecolor=C["edge"], linewidth=0.3)
    for lid, v in sorted(f.items(), key=lambda kv: -kv[1]):
        ax.scatter(*xy[lid], s=v / 18, color=C["accent"], alpha=0.55, edgecolor="white", zorder=4)
        if v > 900:
            name = q("SELECT name FROM location WHERE location_id=?", lid)[0]["name"].replace(" Island", "")
            dens = f" · {v / cult[lid]:.0f}/km²" if cult.get(lid) else ""
            ax.text(xy[lid][0] + 0.15, xy[lid][1], f"{name}: {v:,.0f}{dens}", fontsize=7.5, va="center")
    total = sum(f.values())
    top2 = sum(sorted(f.values())[-2:])
    ax.set_title(f"Farmers by island, 2024-25 (n = {len(f)} islands)\nMiddle + North Andaman hold {100 * top2 / total:.0f}% "
                 f"of {total:,.0f} farmers", loc="left", fontsize=11)
    north_arrow_and_scale(ax)
    india_inset(fig, (0.58, 0.12, 0.34, 0.25))
    save(fig, "fig7_islands_farmers", SRC_NOTE + " Island profiles D10 (DES Island-wise Statistical Outline 2024-25).")


def fig_lulc():
    rows = q("""SELECT location_id, json_extract(dims,'$.lulc_l1') l1, SUM(value) v FROM observation
                WHERE metric_id='lulc_area' AND document_id='D17' GROUP BY location_id, l1""")
    groups = sorted({r["l1"] for r in rows})
    cols = dict(zip(groups, ["#E69F00", "#999999", "#CC79A7", "#009E73", "#56B4E9", "#0072B2"]))
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4))
    for ax, (lid, name) in zip(axes, (("AN_ANDAMAN", "Andaman"), ("AN_NIC", "Nicobar"))):
        d = {r["l1"]: r["v"] for r in rows if r["location_id"] == lid}
        vals = [d.get(g, 0) for g in groups]
        ax.pie(vals, colors=[cols[g] for g in groups], startangle=90, wedgeprops={"width": 0.38, "edgecolor": "white"})
        agri = d.get("Agriculture", 0)
        ax.text(0, 0, f"{name}\n{sum(vals):,.0f} km²\nagri {100 * agri / sum(vals):.1f}%", ha="center", va="center", fontsize=10)
    fig.legend([plt.Rectangle((0, 0), 1, 1, color=cols[g]) for g in groups], groups, loc="lower center", ncol=3, fontsize=8)
    fig.suptitle("Land use / land cover 2015-16: forests dominate, agriculture is under 7% of land", x=0.02, ha="left",
                 fontsize=12, fontweight="bold")
    save(fig, "fig8_lulc_donuts", "Data: NRSC/Bhuvan LULC 2015-16 statistics (D17), n = 28 class × district values.")


# ------------------------------------------------------------------ animations
def _writer(path: Path, fps: int):
    import imageio_ffmpeg
    plt.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    return animation.FFMpegWriter(fps=fps, bitrate=3000) if path.suffix == ".mp4" else animation.PillowWriter(fps=fps)


def seq(n: int, fps: int) -> list[int]:
    """Frame order: the finished picture first (so a paused slide or PDF shows it), then the build-up, then a hold."""
    return [n - 1] * max(1, int(1.5 * fps)) + list(range(n)) + [n - 1] * max(1, 2 * fps)


def save_anim(anim, name: str, fps: int):
    ANIM.mkdir(parents=True, exist_ok=True)
    for ext in (".mp4", ".gif"):
        p = ANIM / f"{name}{ext}"
        anim.save(p, writer=_writer(p, fps), dpi=110 if ext == ".mp4" else 70)
        print(f"  figures/anim/{name}{ext}")
    plt.close(anim._fig)


def anim_paddy_districts():
    paddy = series_by_location("production", "paddy", "district")
    years = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    vmax = max(v for s in paddy.values() for v in s.values())
    fig = plt.figure(figsize=(10, 7.5))
    ax = fig.add_axes([0.02, 0.06, 0.45, 0.86])
    bx = fig.add_axes([0.55, 0.12, 0.4, 0.7])
    xy = loc_xy()

    def frame(i):
        ax.clear()
        bx.clear()
        y = years[i]
        fills = {d: plt.cm.YlOrBr(0.15 + 0.85 * (paddy[d].get(y, 0) / vmax) ** 0.5) for d in paddy}
        base_map(ax, fills)
        for d, (name, _) in DIST.items():
            v = paddy[d].get(y)
            ax.scatter(*xy[d], s=30 + (v or 0) / 25, color=C["paddy"], edgecolor=C["ink"], zorder=4, alpha=0.8)
            ax.text(xy[d][0] + 0.25, xy[d][1], f"{name}\n{v:,.0f} t" if v else name, fontsize=9, va="center")
        ax.set_title(f"Paddy production · {y}", loc="left", fontsize=16, fontweight="bold")
        tot = [sum(paddy[d].get(yy, 0) for d in paddy) for yy in years[: i + 1]]
        bx.plot(range(i + 1), tot, "-o", color=C["paddy"], lw=3)
        bx.set_xlim(-0.3, 4.3)
        bx.set_ylim(0, 18000)
        bx.set_xticks(range(5))
        bx.set_xticklabels(years, rotation=30, fontsize=9)
        bx.set_title("UT total (t)", loc="left")
        bx.text(i, tot[-1] + 600, f"{tot[-1]:,.0f}", ha="center", fontweight="bold")
        fig.texts.clear()
        fig.text(0.01, 0.01, SRC_NOTE, fontsize=6.5, color=C["muted"])
    anim = animation.FuncAnimation(fig, frame, frames=seq(len(years), 1), interval=1200)
    save_anim(anim, "anim1_paddy_districts", fps=1)


def anim_price_calendar():
    M, months = price_matrix(PRICE_ITEMS)
    idx = M / np.nanmean(M, axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    shown = np.full_like(idx, np.nan)
    im = ax.imshow(shown, aspect="auto", cmap="RdBu_r", vmin=0.4, vmax=1.6)
    ax.set_yticks(range(len(PRICE_ITEMS)))
    ax.set_yticklabels([i.replace("_", " ").title() for i in PRICE_ITEMS])
    ax.set_xticks(range(0, len(months), 3))
    ax.set_xticklabels([m[:7] for m in months[::3]], rotation=45, fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.025).set_label("price ÷ 3-yr mean")
    title = ax.set_title("", loc="left", fontsize=13, fontweight="bold")
    fig.text(0.01, 0.01, "Data: DES price statements D11–D13, Port Blair retail survey.", fontsize=7, color=C["muted"])

    def frame(j):
        shown[:] = np.nan
        shown[:, : j + 1] = idx[:, : j + 1]
        im.set_data(shown)
        title.set_text(f"Port Blair retail prices · {months[j][:7]}")
        return (im,)
    anim = animation.FuncAnimation(fig, frame, frames=seq(len(months), 4), interval=250)
    save_anim(anim, "anim2_price_calendar", fps=4)


def anim_islands():
    years = ["2022-23", "2023-24", "2024-25"]
    data = {y: {r["location_id"]: r["v"] for r in q("""SELECT o.location_id, MAX(o.value) v FROM observation o JOIN location l
            ON l.location_id=o.location_id WHERE o.metric_id='farmers_count' AND l.level='island' AND o.period_label=?
            AND o.value IS NOT NULL GROUP BY o.location_id""", y)} for y in years}
    xy = loc_xy()
    fig, ax = plt.subplots(figsize=(6.5, 9))

    def frame(i):
        ax.clear()
        base_map(ax)
        y = years[i]
        for lid, v in data[y].items():
            ax.scatter(*xy[lid], s=v / 15, color=C["accent"], alpha=0.6, edgecolor="white", zorder=4)
            if v > 1400:
                ax.text(xy[lid][0] + 0.15, xy[lid][1], f"{v:,.0f}", fontsize=8, va="center")
        ax.set_title(f"Farmers by island · {y}\nUT total {sum(data[y].values()):,.0f} (n = {len(data[y])} islands)",
                     loc="left", fontsize=13, fontweight="bold")
    anim = animation.FuncAnimation(fig, frame, frames=seq(len(years), 1), interval=1500)
    fig.text(0.01, 0.01, SRC_NOTE, fontsize=6, color=C["muted"])
    save_anim(anim, "anim3_island_farmers", fps=1)


GROUPS = {"maps": [fig_study_area, fig_paddy_hero, fig_islands], "charts": [fig_ut_trends, fig_price_heatmap, fig_lulc],
          "anim": [anim_paddy_districts, anim_price_calendar, anim_islands]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=list(GROUPS) + ["eval"], nargs="*")
    a = ap.parse_args()
    for g in a.only or list(GROUPS) + ["eval"]:
        if g == "eval":
            from scripts.make_eval_figures import main as eval_main
            eval_main()
            continue
        print(f"[{g}]")
        for fn in GROUPS[g]:
            fn()


if __name__ == "__main__":
    main()
