PRAGMA foreign_keys = ON;

CREATE TABLE source_health (
  source_id TEXT PRIMARY KEY
    REFERENCES source_registry(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (
    status IN ('HEALTHY','DEGRADED','UNAVAILABLE')
  ),
  reasons_json TEXT NOT NULL,
  last_checked_at TEXT NOT NULL,
  last_expected_run_at TEXT,
  last_actual_run_at TEXT,
  last_success_at TEXT,
  last_change_at TEXT,
  records_found INTEGER CHECK (
    records_found IS NULL OR records_found >= 0
  ),
  documents_found INTEGER CHECK (
    documents_found IS NULL OR documents_found >= 0
  ),
  adapter_version TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_source_health_status
  ON source_health(status, last_success_at);

CREATE TABLE scheduler_watchdog_events (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL
    REFERENCES source_registry(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (
    event_type IN ('MISSED_RUN','SOURCE_UNAVAILABLE','RECOVERED')
  ),
  expected_at TEXT,
  observed_at TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_watchdog_source_created
  ON scheduler_watchdog_events(source_id, created_at DESC);
