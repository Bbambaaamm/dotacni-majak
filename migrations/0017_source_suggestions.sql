PRAGMA foreign_keys = ON;

CREATE TABLE source_suggestions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  provider_name TEXT,
  note TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (
    status IN ('PENDING_REVIEW','APPROVED','REJECTED')
  ),
  created_at TEXT NOT NULL,
  reviewed_at TEXT,
  review_note TEXT
);

CREATE INDEX idx_source_suggestions_status_created
  ON source_suggestions(status, created_at DESC);
