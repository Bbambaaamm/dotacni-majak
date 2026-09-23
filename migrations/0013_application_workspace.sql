PRAGMA foreign_keys = ON;

CREATE TABLE application_workspaces (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  grant_call_id TEXT NOT NULL REFERENCES grant_calls(id) ON DELETE CASCADE,
  baseline_grant_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (
    status IN ('PREPARING','READY_TO_SUBMIT','SUBMITTED','ARCHIVED')
  ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_workspaces_project
  ON application_workspaces(project_id, updated_at DESC);
CREATE INDEX idx_workspaces_grant
  ON application_workspaces(grant_call_id, updated_at DESC);

CREATE TABLE workspace_tasks (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL
    REFERENCES application_workspaces(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  source TEXT NOT NULL CHECK (
    source IN ('REQUIREMENT','ELIGIBILITY','FINANCE','USER')
  ),
  necessity TEXT NOT NULL CHECK (
    necessity IN ('REQUIRED','CONDITIONAL','RECOMMENDED')
  ),
  status TEXT NOT NULL CHECK (
    status IN ('TODO','IN_PROGRESS','DONE','NOT_APPLICABLE','BLOCKED')
  ),
  blocking INTEGER NOT NULL CHECK (blocking IN (0,1)),
  priority INTEGER NOT NULL,
  reference_id TEXT,
  reason_code TEXT,
  due_at TEXT,
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_workspace_tasks_open
  ON workspace_tasks(workspace_id, status, blocking, priority);

CREATE TABLE workspace_notes (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL
    REFERENCES application_workspaces(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_workspace_notes
  ON workspace_notes(workspace_id, created_at DESC);

CREATE TABLE workspace_documents (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL
    REFERENCES application_workspaces(id) ON DELETE CASCADE,
  requirement_id TEXT,
  filename TEXT NOT NULL,
  storage_ref TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN ('UPLOADED','VERIFIED','REJECTED','SUPERSEDED')
  ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_workspace_documents
  ON workspace_documents(workspace_id, requirement_id, status);
