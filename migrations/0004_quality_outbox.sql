PRAGMA foreign_keys = ON;

CREATE TABLE source_checkpoints (
  source_id TEXT PRIMARY KEY REFERENCES source_registry(id) ON DELETE CASCADE,
  cursor TEXT,
  updated_after TEXT,
  opaque_state_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);

CREATE TABLE ingestion_runs (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('RUNNING','COMPLETED','SOURCE_UNAVAILABLE','PARTIAL_FAILED','DEGRADED','FAILED')),
  records_found INTEGER NOT NULL DEFAULT 0 CHECK (records_found >= 0),
  processed INTEGER NOT NULL DEFAULT 0 CHECK (processed >= 0),
  skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped >= 0),
  gone INTEGER NOT NULL DEFAULT 0 CHECK (gone >= 0),
  failed INTEGER NOT NULL DEFAULT 0 CHECK (failed >= 0),
  destructive_changes_allowed INTEGER NOT NULL DEFAULT 1 CHECK (destructive_changes_allowed IN (0,1))
);

CREATE INDEX idx_ingestion_runs_source_started
ON ingestion_runs(source_id, started_at DESC);

CREATE TABLE ingestion_items (
  id TEXT PRIMARY KEY,
  ingestion_run_id TEXT NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
  source_record_id TEXT REFERENCES source_records(id) ON DELETE SET NULL,
  external_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN (
    'DISCOVERED','FETCHING','FETCHED','SNAPSHOTTED','PARSED','EXTRACTED',
    'NORMALIZED','VALIDATED','STAGED','PUBLISHED','INDEXED','COMPLETED',
    'RETRYABLE_FAILED','QUARANTINED','PERMANENT_FAILED'
  )),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (ingestion_run_id, external_id)
);

CREATE INDEX idx_ingestion_items_run_state
ON ingestion_items(ingestion_run_id, state);

CREATE TABLE data_quality_issues (
  id TEXT PRIMARY KEY,
  ingestion_run_id TEXT NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_quality_issues_run
ON data_quality_issues(ingestion_run_id);

CREATE TABLE quarantine_items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  source_record_id TEXT REFERENCES source_records(id) ON DELETE SET NULL,
  external_id TEXT,
  reason TEXT NOT NULL CHECK (reason IN (
    'VALIDATION_FAILED','SCHEMA_MISMATCH','QUALITY_GATE',
    'DUPLICATE_AMBIGUOUS','SECURITY_REJECTED','OTHER'
  )),
  details TEXT,
  payload_ref TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_note TEXT
);

CREATE INDEX idx_quarantine_source_unresolved
ON quarantine_items(source_id, resolved_at);

CREATE TABLE outbox_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'SEARCH_REINDEX_REQUIRED',
    'VECTOR_REINDEX_REQUIRED',
    'CHANGE_DETECTION_REQUIRED',
    'WATCH_REEVALUATION_REQUIRED',
    'NOTIFICATION_REQUIRED'
  )),
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('PENDING','PROCESSING','DELIVERED','FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  last_error TEXT
);

CREATE INDEX idx_outbox_pending
ON outbox_events(status, available_at);

CREATE INDEX idx_outbox_aggregate
ON outbox_events(aggregate_type, aggregate_id);
