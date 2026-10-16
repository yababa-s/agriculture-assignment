-- Agricultural Knowledge Base, Andaman & Nicobar Islands (schema v1, frozen for Phase 2)
--
-- Design: a star schema. Every extracted number is ONE row in `observation`
-- (the fact table), keyed to lookup tables for commodity, location, metric and
-- unit, and to full provenance (document, page, table, row/column label, raw
-- text, extraction run, agent). The team's proposed Production / Price /
-- Source tables are kept as views (v_production, v_price) and the `source` +
-- `document` tables.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- provenance
CREATE TABLE IF NOT EXISTS source (            -- publisher / portal
    source_id      TEXT PRIMARY KEY,           -- e.g. SRC_DES
    name           TEXT NOT NULL,
    portal_url     TEXT,
    source_type    TEXT NOT NULL,              -- government_statistical_publication, geoportal, ...
    license        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document (          -- one corpus file (mirrors data/manifest.csv)
    document_id     TEXT PRIMARY KEY,          -- D01..D20, U01.. for unseen docs
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    file_name       TEXT NOT NULL,
    relative_path   TEXT,
    document_url    TEXT,
    source_group    TEXT NOT NULL,             -- G1..G8, decides the agent
    period_label    TEXT,
    modality        TEXT NOT NULL,             -- pdf_digital | pdf_scanned | pdf_mixed | image | html
    languages       TEXT NOT NULL,             -- en | en+hi ...
    scripts         TEXT,
    legacy_font     INTEGER NOT NULL DEFAULT 0,
    pages           INTEGER,
    sha256          TEXT NOT NULL UNIQUE,      -- same file ingested twice = same document
    collection_date TEXT,
    license         TEXT
);

CREATE TABLE IF NOT EXISTS agent (
    agent_id    TEXT PRIMARY KEY,              -- e.g. matrix_table_agent
    description TEXT NOT NULL,
    version     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_run (
    run_id                TEXT PRIMARY KEY,    -- uuid
    batch_id              TEXT NOT NULL,       -- one orchestrator invocation
    document_id           TEXT NOT NULL REFERENCES document(document_id),
    agent_id              TEXT NOT NULL REFERENCES agent(agent_id),
    model_name            TEXT,                -- base LLM (NULL = rules only)
    adapter               TEXT,                -- LoRA adapter path/version (NULL = base model)
    started_at            TEXT NOT NULL,
    finished_at           TEXT,
    status                TEXT NOT NULL CHECK (status IN ('running','loaded','partial','failed','needs_review','skipped')),
    attempts              INTEGER NOT NULL DEFAULT 1,
    n_extracted           INTEGER DEFAULT 0,
    n_loaded              INTEGER DEFAULT 0,
    n_rejected            INTEGER DEFAULT 0,
    n_llm_calls           INTEGER DEFAULT 0,
    manual_interventions  INTEGER NOT NULL DEFAULT 0,
    trace_path            TEXT,                -- logs/traces/<run_id>.jsonl
    error                 TEXT
);

-- ---------------------------------------------------------------- dimensions
CREATE TABLE IF NOT EXISTS location (
    location_id  TEXT PRIMARY KEY,             -- e.g. AN, AN_SA (district), AN_SA_PB (tehsil), ISL_SWARAJ
    name         TEXT NOT NULL,
    name_hi      TEXT,
    level        TEXT NOT NULL CHECK (level IN ('country','ut','district','tehsil','agri_zone','island','market')),
    parent_id    TEXT REFERENCES location(location_id),
    lgd_code     TEXT,                         -- Local Government Directory code where known
    area_sq_km   REAL
);

CREATE TABLE IF NOT EXISTS commodity (         -- crops AND market items (eggs, fish, rice ...)
    commodity_id TEXT PRIMARY KEY,             -- e.g. paddy, black_pepper
    name         TEXT NOT NULL,
    name_hi      TEXT,
    category     TEXT NOT NULL,                -- cereal, pulse, oilseed, spice, plantation, fruit, vegetable,
                                               -- root_crop, flower, sugar, livestock_product, fish, processed_food, aggregate
    is_aggregate INTEGER NOT NULL DEFAULT 0    -- 1 for "Total pulses", "Vegetables" etc.
);

CREATE TABLE IF NOT EXISTS unit (
    unit_id        TEXT PRIMARY KEY,           -- ha, mt, inr_per_kg ...
    symbol         TEXT NOT NULL,
    dimension      TEXT NOT NULL,              -- area, mass, count, price, money, ratio, energy
    base_unit_id   TEXT REFERENCES unit(unit_id),
    to_base_factor REAL                        -- value_in_base = value * to_base_factor
);

CREATE TABLE IF NOT EXISTS metric (
    metric_id    TEXT PRIMARY KEY,             -- area_cultivated, production, yield, retail_price ...
    name         TEXT NOT NULL,
    domain       TEXT NOT NULL,                -- production, price, inputs, infrastructure, land_use, census, finance, demography
    default_unit TEXT REFERENCES unit(unit_id),
    description  TEXT
);

-- Every surface form seen in documents (English variants, Hindi, abbreviations).
CREATE TABLE IF NOT EXISTS alias (
    alias        TEXT NOT NULL,                -- normalised lower-case surface form
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('commodity','location','metric','unit')),
    entity_id    TEXT NOT NULL,
    lang         TEXT NOT NULL DEFAULT 'en',
    origin       TEXT NOT NULL DEFAULT 'seed', -- seed | llm | manual
    PRIMARY KEY (alias, entity_type, entity_id)
);

-- ---------------------------------------------------------------- facts
CREATE TABLE IF NOT EXISTS observation (
    obs_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_id       TEXT NOT NULL REFERENCES metric(metric_id),
    commodity_id    TEXT REFERENCES commodity(commodity_id),    -- NULL for non-commodity metrics (population, LULC)
    location_id     TEXT NOT NULL REFERENCES location(location_id),
    period_label    TEXT NOT NULL,             -- as reported: '2023-24', 'January 2024'
    period_type     TEXT NOT NULL CHECK (period_type IN ('agri_year','fiscal_year','calendar_year','month','census_round','as_on_date')),
    period_start    TEXT NOT NULL,             -- ISO date, enables temporal range queries
    period_end      TEXT NOT NULL,
    season          TEXT,                      -- kharif / rabi / NULL when not reported
    dims            TEXT NOT NULL DEFAULT '{}',-- extra qualifiers as JSON, e.g. {"holding_size":"1.0-2.0","holder":"individual"}
    value           REAL,                      -- normalised value in unit_id; NULL when missing
    unit_id         TEXT REFERENCES unit(unit_id),
    value_raw       TEXT NOT NULL,             -- exact cell text as printed
    unit_raw        TEXT,
    missing_reason  TEXT CHECK (missing_reason IN ('not_available','nil','not_applicable','blank','unparseable') OR missing_reason IS NULL),
    is_total_row    INTEGER NOT NULL DEFAULT 0,-- 1 when the source row/column is itself an aggregate
    -- provenance
    document_id     TEXT NOT NULL REFERENCES document(document_id),
    page            INTEGER,                   -- 1-based page in the file
    table_ref       TEXT,                      -- 'Table 3.2' or 'p3_t1'
    row_label       TEXT,                      -- label as printed (Hindi decoded)
    col_label       TEXT,
    run_id          TEXT NOT NULL REFERENCES extraction_run(run_id),
    agent_id        TEXT NOT NULL REFERENCES agent(agent_id),
    -- quality
    confidence      REAL,                      -- 0..1 (rule path = 1.0, LLM path = self/validator score)
    validation      TEXT NOT NULL DEFAULT 'ok' CHECK (validation IN ('ok','warning','error')),
    validation_note TEXT,
    dedup_key       TEXT NOT NULL UNIQUE,      -- sha1(metric|commodity|location|period|dims|document|page|table|row|col)
    CHECK (value IS NOT NULL OR missing_reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_obs_lookup ON observation(metric_id, commodity_id, location_id, period_start);
CREATE INDEX IF NOT EXISTS ix_obs_doc ON observation(document_id, page);
CREATE INDEX IF NOT EXISTS ix_obs_run ON observation(run_id);

-- Qualitative facts from narrative documents (schemes, initiatives, clusters).
CREATE TABLE IF NOT EXISTS text_fact (
    fact_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT NOT NULL,                -- e.g. scheme name
    predicate    TEXT NOT NULL,                -- provides_subsidy_for, objective, production_cluster ...
    object       TEXT NOT NULL,
    location_id  TEXT REFERENCES location(location_id),
    period_label TEXT,
    document_id  TEXT NOT NULL REFERENCES document(document_id),
    page         INTEGER,
    evidence     TEXT NOT NULL,                -- verbatim span supporting the fact
    run_id       TEXT NOT NULL REFERENCES extraction_run(run_id),
    agent_id     TEXT NOT NULL REFERENCES agent(agent_id),
    dedup_key    TEXT NOT NULL UNIQUE
);

-- Page text kept for provenance look-ups and Phase 3 retrieval (RAG).
CREATE TABLE IF NOT EXISTS document_chunk (
    chunk_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  TEXT NOT NULL REFERENCES document(document_id),
    page         INTEGER NOT NULL,
    text         TEXT NOT NULL,                -- Kruti Dev already converted where detected
    UNIQUE (document_id, page)
);

-- Rows the validator refused, kept for review instead of silently dropped.
CREATE TABLE IF NOT EXISTS rejected_record (
    rej_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES extraction_run(run_id),
    payload     TEXT NOT NULL,                 -- JSON of the candidate record
    reason      TEXT NOT NULL
);

-- ---------------------------------------------------------------- views
-- The team's original "Production" entity: one row per crop x location x period x source.
CREATE VIEW IF NOT EXISTS v_production AS
SELECT o.commodity_id, c.name AS crop_name, o.location_id, l.name AS location, l.level AS location_level,
       o.period_label AS year, o.season,
       MAX(CASE WHEN o.metric_id = 'area_cultivated' THEN o.value END) AS area_ha,
       MAX(CASE WHEN o.metric_id = 'production'      THEN o.value END) AS production,
       MAX(CASE WHEN o.metric_id = 'production'      THEN o.unit_id END) AS production_unit,
       MAX(CASE WHEN o.metric_id = 'yield'           THEN o.value END) AS yield,
       o.document_id AS source_document, MIN(o.page) AS page, o.table_ref
FROM observation o
JOIN commodity c ON c.commodity_id = o.commodity_id
JOIN location  l ON l.location_id  = o.location_id
WHERE o.metric_id IN ('area_cultivated','production','yield')
GROUP BY o.commodity_id, o.location_id, o.period_label, o.season, o.document_id, o.table_ref;

-- The team's original "Price" entity.
CREATE VIEW IF NOT EXISTS v_price AS
SELECT o.obs_id AS price_id, o.commodity_id, c.name AS commodity, l.name AS market_location,
       o.period_label AS time_period, o.period_start,
       CASE WHEN o.metric_id = 'retail_price'       THEN o.value END AS retail_price,
       CASE WHEN o.metric_id = 'wholesale_price'    THEN o.value END AS wholesale_price,
       CASE WHEN o.metric_id = 'farm_harvest_price' THEN o.value END AS farm_harvest_price,
       o.unit_raw AS unit, o.document_id AS source_document, o.page
FROM observation o
JOIN commodity c ON c.commodity_id = o.commodity_id
JOIN location  l ON l.location_id  = o.location_id
WHERE o.metric_id IN ('retail_price','wholesale_price','farm_harvest_price');

-- Same fact reported by two different documents with different values (cross-source consistency).
CREATE VIEW IF NOT EXISTS v_conflict AS
SELECT a.metric_id, a.commodity_id, a.location_id, a.period_label, a.dims,
       a.document_id AS doc_a, a.page AS page_a, a.value AS value_a,
       b.document_id AS doc_b, b.page AS page_b, b.value AS value_b,
       ROUND(100.0 * ABS(a.value - b.value) / NULLIF(ABS(a.value), 0), 2) AS pct_diff
FROM observation a
JOIN observation b
  ON a.metric_id = b.metric_id AND a.commodity_id IS b.commodity_id AND a.location_id = b.location_id
 AND a.period_label = b.period_label AND a.dims = b.dims AND a.unit_id IS b.unit_id
 AND a.document_id < b.document_id
WHERE a.value IS NOT NULL AND b.value IS NOT NULL AND ABS(a.value - b.value) > 0.01 * ABS(a.value);

-- Provenance view: every number with its full citation.
CREATE VIEW IF NOT EXISTS v_provenance AS
SELECT o.obs_id, o.metric_id, o.commodity_id, o.location_id, o.period_label, o.value, o.unit_id, o.value_raw,
       d.file_name, d.document_url, s.name AS publisher, o.page, o.table_ref, o.row_label, o.col_label,
       r.run_id, r.agent_id, r.model_name, r.adapter, r.started_at
FROM observation o
JOIN document d ON d.document_id = o.document_id
JOIN source   s ON s.source_id   = d.source_id
JOIN extraction_run r ON r.run_id = o.run_id;
