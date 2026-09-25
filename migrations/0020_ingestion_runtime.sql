PRAGMA foreign_keys = ON;

CREATE TABLE source_checkpoints (
  source_code TEXT PRIMARY KEY,
  cursor TEXT,
  updated_after TEXT,
  opaque_state_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);

CREATE TABLE ingestion_runs (
  id TEXT PRIMARY KEY,
  source_code TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN (
      'RUNNING',
      'COMPLETED',
      'SOURCE_UNAVAILABLE',
      'PARTIAL_FAILED',
      'LOCKED',
      'FAILED'
    )
  ),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  checkpoint_before_json TEXT,
  checkpoint_after_json TEXT,
  processed INTEGER NOT NULL DEFAULT 0 CHECK (processed >= 0),
  skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped >= 0),
  gone INTEGER NOT NULL DEFAULT 0 CHECK (gone >= 0),
  failed INTEGER NOT NULL DEFAULT 0 CHECK (failed >= 0),
  pages INTEGER NOT NULL DEFAULT 0 CHECK (pages >= 0),
  last_error TEXT
);

CREATE INDEX idx_ingestion_runs_source_started
  ON ingestion_runs(source_code, started_at DESC);

CREATE INDEX idx_ingestion_runs_status_started
  ON ingestion_runs(status, started_at DESC);

CREATE TABLE ingestion_items (
  source_code TEXT NOT NULL,
  external_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (
    state IN (
      'DISCOVERED','FETCHING','FETCHED','SNAPSHOTTED','PARSED',
      'EXTRACTED','NORMALIZED','VALIDATED','STAGED','PUBLISHED',
      'INDEXED','COMPLETED','RETRYABLE_FAILED','QUARANTINED',
      'PERMANENT_FAILED'
    )
  ),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error TEXT,
  first_seen_run_id TEXT REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  last_run_id TEXT REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(source_code, external_id)
);

CREATE INDEX idx_ingestion_items_source_state
  ON ingestion_items(source_code, state, updated_at);

CREATE INDEX idx_ingestion_items_last_run
  ON ingestion_items(last_run_id, state);

CREATE TABLE ingestion_locks (
  source_code TEXT PRIMARY KEY,
  lease_owner TEXT NOT NULL,
  lease_expires_at TEXT NOT NULL,
  acquired_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_ingestion_locks_expiry
  ON ingestion_locks(lease_expires_at);
