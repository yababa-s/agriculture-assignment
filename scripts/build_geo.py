"""Build the geospatial layer: district and island polygons, an India outline, and point coordinates.

Inputs (downloaded once with --download into data/geo/src/, git-ignored):
  * India-Districts-2011Census.shp  Census 2011 district boundaries digitised from Survey of India maps
  * india-soi.geojson               India outline dissolved from the same Survey of India based data
  Both from the DataMeet maps repository (https://github.com/datameet/maps), which republishes
  the official boundaries; recorded as source G9_GEO in docs/geo.md.
  * data/geo/gazetteer.csv          team-geocoded points (HQs, islands, market); every point is
                                    checked against the district polygons below.

Outputs (small, committed):
  data/geo/an_districts.geojson   3 districts (simplified)
  data/geo/an_islands.geojson     island polygons: each land part assigned to the nearest gazetteer island
  data/geo/india_outline.geojson  India outline for inset maps (simplified)
  data/geo/locations.csv          location_id, lat, lon, district check, snap distance

Run:  python scripts/build_geo.py [--download]
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapely.geometry import MultiPolygon, Point, mapping, shape  # noqa: E402

from agri import config  # noqa: E402

GEO = config.GEO_DIR
SRC = GEO / "src"
DATAMEET = "https://raw.githubusercontent.com/datameet/maps/master"
FILES = {
    "India-Districts-2011Census.shp": f"{DATAMEET}/Survey-of-India-Index-Maps/Boundaries/India-Districts-2011Census.shp",
    "India-Districts-2011Census.dbf": f"{DATAMEET}/Survey-of-India-Index-Maps/Boundaries/India-Districts-2011Census.dbf",
    "India-Districts-2011Census.shx": f"{DATAMEET}/Survey-of-India-Index-Maps/Boundaries/India-Districts-2011Census.shx",
    "India-Districts-2011Census.prj": f"{DATAMEET}/Survey-of-India-Index-Maps/Boundaries/India-Districts-2011Census.prj",
    "india-soi.geojson": f"{DATAMEET}/Country/india-soi.geojson",
}
DISTRICT_IDS = {"Nicobar": "AN_NIC", "South Andaman": "AN_SA", "North & Middle Andaman": "AN_NMA"}


def download() -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dst = SRC / name
        if not dst.exists():
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, dst)


def read_districts() -> dict[str, MultiPolygon]:
    """Read the A&N districts from the shapefile with pyshp-free parsing via geopandas when present."""
    try:
        import geopandas as gpd
        df = gpd.read_file(SRC / "India-Districts-2011Census.shp")
        df = df[df.ST_NM.str.contains("Andaman")]
        return {DISTRICT_IDS[r.DISTRICT]: r.geometry for r in df.itertuples()}
    except ImportError:
        sys.exit("build_geo.py needs geopandas only when rebuilding from the raw shapefile: pip install geopandas")


def fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="fetch the raw boundary files first")
    ap.add_argument("--tolerance", type=float, default=0.002, help="simplification tolerance in degrees")
    a = ap.parse_args()
    if a.download:
        download()
    districts = read_districts()

    # districts
    feats = [{"type": "Feature", "properties": {"location_id": lid},
              "geometry": mapping(g.simplify(a.tolerance, preserve_topology=True))} for lid, g in districts.items()]
    (GEO / "an_districts.geojson").write_text(json.dumps(fc(feats)))

    # India outline (for the inset map)
    india = json.loads((SRC / "india-soi.geojson").read_text())
    geom = shape(india["features"][0]["geometry"]).simplify(0.05, preserve_topology=True)
    (GEO / "india_outline.geojson").write_text(json.dumps(fc([{"type": "Feature", "properties": {"name": "India"},
                                                                "geometry": mapping(geom)}])))

    # points: check each against the district polygons
    conn = sqlite3.connect(config.DB_PATH)
    parent = dict(conn.execute("SELECT location_id, parent_id FROM location"))

    def district_of(lid: str | None) -> str | None:
        while lid and lid not in districts:
            lid = parent.get(lid)
        return lid

    parts = [(lid, p) for lid, g in districts.items() for p in getattr(g, "geoms", [g])]
    rows, island_pts = [], {}
    for r in csv.DictReader((GEO / "gazetteer.csv").open()):
        lid = r["location_id"]
        if not r["lat"]:
            g = districts[lid]
            c = max(getattr(g, "geoms", [g]), key=lambda p: p.area).representative_point()  # main island
            lat, lon = round(c.y, 4), round(c.x, 4)
        else:
            lat, lon = float(r["lat"]), float(r["lon"])
        pt = Point(lon, lat)
        poly_d, part = min(parts, key=lambda x: x[1].distance(pt))
        snap_km = round(part.distance(pt) * 111.0, 2)
        expected = district_of(lid)
        ok = expected is None or expected == poly_d
        if not ok or snap_km > 5:
            print(f"WARNING {lid}: point lies in {poly_d} (expected {expected}), {snap_km} km from land")
        rows.append({"location_id": lid, "lat": lat, "lon": lon, "point_type": r["point_type"],
                     "district_check": "ok" if ok else "mismatch", "km_to_land": snap_km, "note": r["note"]})
        if r["point_type"] == "island":
            island_pts[lid] = pt
    with (GEO / "locations.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # islands: every land part goes to the nearest gazetteer island (several small parts may share an owner)
    owned: dict[str, list] = {}
    for _lid, p in parts:
        rp = p.representative_point()
        owner = min(island_pts, key=lambda i: island_pts[i].distance(rp))
        owned.setdefault(owner, []).append(p)
    feats = [{"type": "Feature", "properties": {"location_id": lid, "n_parts": len(ps)},
              "geometry": mapping(MultiPolygon(ps).simplify(a.tolerance, preserve_topology=True))}
             for lid, ps in sorted(owned.items())]
    (GEO / "an_islands.geojson").write_text(json.dumps(fc(feats)))
    print(f"districts 3, islands with polygons {len(owned)}/{len(island_pts)}, points {len(rows)} "
          f"(all district checks {'ok' if all(r['district_check'] == 'ok' for r in rows) else 'NOT ok'})")


if __name__ == "__main__":
    main()
