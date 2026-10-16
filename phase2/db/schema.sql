PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_document (
  doc_id TEXT PRIMARY KEY,
  file_name TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  source_group TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT,
  language TEXT NOT NULL,
  modality TEXT NOT NULL,
  license_note TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  pages INTEGER,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_run (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  attempted INTEGER NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0,
  manual_interventions INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS page_text (
  doc_id TEXT NOT NULL REFERENCES source_document(doc_id),
  page INTEGER NOT NULL,
  text TEXT NOT NULL,
  PRIMARY KEY (doc_id, page)
);

CREATE TABLE IF NOT EXISTS table_cell (
  cell_id INTEGER PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES source_document(doc_id),
  run_id TEXT NOT NULL REFERENCES extraction_run(run_id),
  agent_id TEXT NOT NULL,
  page INTEGER NOT NULL,
  table_no INTEGER NOT NULL,
  row_no INTEGER NOT NULL,
  col_no INTEGER NOT NULL,
  value_raw TEXT NOT NULL,
  value_numeric REAL,
  UNIQUE (doc_id, page, table_no, row_no, col_no)
);

CREATE TABLE IF NOT EXISTS observation (
  obs_id INTEGER PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES source_document(doc_id),
  run_id TEXT NOT NULL REFERENCES extraction_run(run_id),
  agent_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  commodity TEXT NOT NULL,
  location TEXT NOT NULL,
  period TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  value_raw TEXT NOT NULL,
  page INTEGER NOT NULL,
  table_no INTEGER NOT NULL,
  row_no INTEGER NOT NULL,
  col_no INTEGER NOT NULL,
  evidence TEXT NOT NULL,
  UNIQUE (doc_id, metric, commodity, location, period, page, table_no, row_no, col_no)
);

CREATE TABLE IF NOT EXISTS text_fact (
  fact_id INTEGER PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES source_document(doc_id),
  run_id TEXT NOT NULL REFERENCES extraction_run(run_id),
  agent_id TEXT NOT NULL,
  page INTEGER NOT NULL,
  fact_type TEXT NOT NULL,
  evidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_trace (
  trace_id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES extraction_run(run_id),
  doc_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  event TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_observation_query ON observation(metric, commodity, location, period);
CREATE INDEX IF NOT EXISTS ix_cell_source ON table_cell(doc_id, page, table_no);
CREATE INDEX IF NOT EXISTS ix_trace_run ON agent_trace(run_id, doc_id);

CREATE VIEW IF NOT EXISTS v_provenance AS
SELECT o.metric, o.commodity, o.location, o.period, o.value, o.unit, o.value_raw,
       d.file_name, d.source_name, d.source_type, o.page, o.table_no, o.row_no, o.col_no,
       o.agent_id, o.run_id, o.evidence
FROM observation o JOIN source_document d USING (doc_id);
