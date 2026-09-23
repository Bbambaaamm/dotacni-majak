PRAGMA foreign_keys = ON;

CREATE TABLE data_quality_issues (
  id TEXT PRIMARY KEY,
  source_id TEXT REFERENCES source_registry(id) ON DELETE CASCADE,
  source_run_id TEXT REFERENCES source_runs(id) ON DELETE CASCADE,
  severity TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','ERROR','CRITICAL')),
  rule_code TEXT NOT NULL,
  message TEXT NOT NULL,
  details_json TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE INDEX idx_quality_issues_source_created
  ON data_quality_issues(source_id, created_at DESC);
CREATE INDEX idx_quality_issues_unresolved
  ON data_quality_issues(resolved_at, severity);

CREATE TABLE quarantine_items (
  id TEXT PRIMARY KEY,
  source_id TEXT REFERENCES source_registry(id) ON DELETE CASCADE,
  source_run_id TEXT REFERENCES source_runs(id) ON DELETE SET NULL,
  external_id TEXT,
  reason TEXT NOT NULL CHECK (
    reason IN (
      'VALIDATION_FAILED',
      'SCHEMA_MISMATCH',
      'QUALITY_GATE',
      'DUPLICATE_AMBIGUOUS',
      'SECURITY_REJECTED',
      'OTHER'
    )
  ),
  details_json TEXT,
  payload_ref TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_note TEXT
);

CREATE INDEX idx_quarantine_open
  ON quarantine_items(source_id, resolved_at, created_at DESC);

CREATE TABLE outbox_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL CHECK (
    event_type IN (
      'SEARCH_REINDEX_REQUIRED',
      'VECTOR_REINDEX_REQUIRED',
      'CHANGE_DETECTION_REQUIRED',
      'WATCH_REEVALUATION_REQUIRED',
      'NOTIFICATION_REQUIRED'
    )
  ),
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
    status IN ('PENDING','PROCESSING','DELIVERED','FAILED')
  ),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  last_error TEXT
);

CREATE INDEX idx_outbox_pending
  ON outbox_events(status, available_at, created_at);
CREATE INDEX idx_outbox_aggregate
  ON outbox_events(aggregate_type, aggregate_id, created_at DESC);
