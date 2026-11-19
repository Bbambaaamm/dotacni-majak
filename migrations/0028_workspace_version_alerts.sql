-- One application per project/call; retries never replace its immutable baseline.
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_project_call
  ON application_workspaces(project_id, grant_call_id);

-- Owner-only, persisted version-review notices, generated on workspace read.
CREATE TABLE IF NOT EXISTS workspace_version_alerts (
  workspace_id TEXT NOT NULL REFERENCES application_workspaces(id) ON DELETE CASCADE,
  grant_call_version_id TEXT NOT NULL REFERENCES grant_call_versions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (workspace_id, grant_call_version_id)
);
