PRAGMA foreign_keys = ON;

ALTER TABLE projects ADD COLUMN owner_user_id TEXT;

CREATE INDEX idx_projects_owner_updated
  ON projects(owner_user_id, updated_at DESC);

CREATE TABLE project_share_links (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_user_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL DEFAULT 'PROJECT_READ_ONLY'
    CHECK (scope IN ('PROJECT_READ_ONLY')),
  created_at TEXT NOT NULL,
  expires_at TEXT,
  revoked_at TEXT,
  last_accessed_at TEXT,
  CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE INDEX idx_project_share_links_project
  ON project_share_links(project_id, created_at DESC);

CREATE INDEX idx_project_share_links_owner
  ON project_share_links(owner_user_id, created_at DESC);

CREATE INDEX idx_project_share_links_active
  ON project_share_links(token_hash, revoked_at, expires_at);

CREATE TABLE share_audit_events (
  id TEXT PRIMARY KEY,
  share_link_id TEXT REFERENCES project_share_links(id) ON DELETE SET NULL,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  actor_user_id TEXT,
  event_type TEXT NOT NULL CHECK (
    event_type IN (
      'CREATED',
      'RESOLVED',
      'REVOKED',
      'DENIED_OWNER_MISMATCH',
      'DENIED_REVOKED',
      'DENIED_EXPIRED',
      'DENIED_UNKNOWN_TOKEN'
    )
  ),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_share_audit_project_created
  ON share_audit_events(project_id, created_at DESC);

CREATE INDEX idx_share_audit_link_created
  ON share_audit_events(share_link_id, created_at DESC);
