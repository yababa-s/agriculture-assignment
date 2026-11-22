# Geospatial layer (schema v2)

Phase 3 adds coordinates to every place in the knowledge base and polygon layers for maps. Spatial queries
(`nearby`, distance ranking) and every map in the report, poster, slides and app use this layer.

## Sources (recorded as reference data, group G9_GEO)

| Layer | File in repo | Source | Licence / terms |
|---|---|---|---|
| District boundaries (3 A&N districts) | `data/geo/an_districts.geojson` | Census of India 2011 district boundaries digitised from Survey of India maps, republished by DataMeet (`Survey-of-India-Index-Maps/Boundaries/India-Districts-2011Census.shp`), https://github.com/datameet/maps, accessed 2026-11-23 | DataMeet: CC BY 2.5 India / ODbL (attribution) |
| Island polygons | `data/geo/an_islands.geojson` | the land parts of the district layer, each assigned to the nearest gazetteer island | derived from the above |
| India outline (inset maps) | `data/geo/india_outline.geojson` | DataMeet `Country/india-soi.geojson`: India dissolved from the Survey of India based boundaries, i.e. India's official boundary including J&K and Ladakh | CC BY-SA 2.5 / ODbL |
| Point coordinates (53 places) | `data/geo/gazetteer.csv` → `data/geo/locations.csv` | team-geocoded HQ towns, island centres, market; district points = centre of the main island of the district polygon | team work |

**Why not GADM / Natural Earth / OSM country outlines:** they do not show India's official boundary. Indian
law and the course brief require Survey of India approved boundaries on any map of India, so the inset uses
the Survey of India based outline above.

## Quality check

`scripts/build_geo.py` checks every gazetteer point against the district polygons: the point must fall in
(or within 5 km of the coast of) the district its parent chain says it belongs to. Result: **53/53 points in
the expected district**, largest distance to land 2.2 km (Aves Island, a 0.2 km² islet). Each of the 31
islands received at least one polygon part.

Accuracy: HQ and island points are approximate centres (about ±5 km), adequate for district-level maps and
50–200 km distance queries, not for field-level work. Agriculture zones and tehsils have no published
polygons, so they are drawn as points (their HQ town) and labelled that way.

## Schema change (v1 → v2)

```sql
ALTER TABLE location ADD COLUMN lat REAL;        -- WGS84
ALTER TABLE location ADD COLUMN lon REAL;
ALTER TABLE location ADD COLUMN geo_source TEXT; -- e.g. "island: team gazetteer"
CREATE TABLE meta_schema (key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- schema_version = v2
```

Upgrade an existing v1 file in place: `python -m agri.db.migrate --db db/34_AN_knowledgebase_v1.sqlite`.
Rebuild the layer: `python scripts/build_geo.py --download` (downloads the raw shapefile into `data/geo/src/`).
