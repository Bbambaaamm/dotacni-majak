PRAGMA foreign_keys = ON;

-- User-uploaded private attachments for application workspaces.
-- These are USER-OWNED blobs in a private R2 bucket, completely separate from
-- official source documents (source_documents / document_versions). The API
-- layer enforces owner-capability authorization, MIME/size limits, and an audit
-- trail. Raw file content is never logged or exposed as a public URL.

CREATE TABLE user_document_attachments (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_user_id TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0 AND size_bytes <= 10485760),
  status TEXT NOT NULL DEFAULT 'UPLOADED' CHECK (status IN ('UPLOADED','REJECTED','DELETED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (project_id, storage_key)
);

CREATE INDEX idx_user_document_attachments_owner
  ON user_document_attachments(owner_user_id, created_at DESC);

CREATE INDEX idx_user_document_attachments_project
  ON user_document_attachments(project_id, status, created_at DESC);

-- User-document audit events. Raw file content / storage key is never stored in
-- this table; it records only the metadata mutation (CREATE/DELETE) and actor.
CREATE TABLE user_document_attachment_events (
  id TEXT PRIMARY KEY,
  attachment_id TEXT NOT NULL REFERENCES user_document_attachments(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  actor_user_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (
    event_type IN ('CREATED','DELETED','STATUS_CHANGED')
  ),
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_user_document_attachment_events_owner
  ON user_document_attachment_events(actor_user_id, created_at DESC);

CREATE INDEX idx_user_document_attachment_events_attachment
  ON user_document_attachment_events(attachment_id, created_at DESC);
