PRAGMA foreign_keys = ON;

CREATE TABLE project_owner_capabilities (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  generation INTEGER NOT NULL DEFAULT 1 CHECK (generation >= 1),
  created_at TEXT NOT NULL,
  rotated_at TEXT,
  last_used_at TEXT,
  revoked_at TEXT
);

CREATE INDEX idx_project_owner_capability_hash
  ON project_owner_capabilities(token_hash, revoked_at);

CREATE TABLE project_owner_audit_events (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL CHECK (
    event_type IN (
      'CREATED',
      'VERIFIED',
      'ROTATED',
      'REVOKED',
      'DENIED_UNKNOWN',
      'DENIED_REVOKED',
      'DENIED_PROJECT_MISMATCH'
    )
  ),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_project_owner_audit_project_created
  ON project_owner_audit_events(project_id, created_at DESC);
