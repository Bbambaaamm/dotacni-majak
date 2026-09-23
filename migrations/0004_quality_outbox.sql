PRAGMA foreign_keys = ON;

CREATE TABLE data_quality_issues (
  id TEXT PRIMARY KEY,
  source_run_id TEXT REFERENCES source_runs(id) ON DELETE CASCADE,
  source_record_id TEXT REFERENCES source_records(id) ON DELETE SET NULL,
  severity TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','ERROR','CRITICAL')),
  reason_code TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_quality_run_severity
  ON data_quality_issues(source_run_id, severity);

CREATE TABLE quarantine_items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  external_id TEXT,
  reason_code TEXT NOT NULL,
  detail TEXT,
  payload_ref TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_note TEXT
);

CREATE INDEX idx_quarantine_source_resolved
  ON quarantine_items(source_id, resolved_at);

CREATE TABLE outbox_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
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

CREATE INDEX idx_outbox_delivery
  ON outbox_events(status, available_at);
