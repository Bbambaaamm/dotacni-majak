PRAGMA foreign_keys = ON;

CREATE TABLE quarantine_reprocess_attempts (
  id TEXT PRIMARY KEY,
  quarantine_item_id TEXT NOT NULL
    REFERENCES quarantine_items(id) ON DELETE CASCADE,
  parser_version TEXT,
  requested_by TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN ('REQUESTED','RUNNING','SUCCEEDED','FAILED')
  ),
  requested_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  last_error TEXT
);

CREATE INDEX idx_quarantine_reprocess_item
  ON quarantine_reprocess_attempts(quarantine_item_id, requested_at DESC);

CREATE INDEX idx_quarantine_reprocess_status
  ON quarantine_reprocess_attempts(status, requested_at);
