PRAGMA foreign_keys = ON;

CREATE TABLE relevance_feedback (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  judgment TEXT NOT NULL CHECK (
    judgment IN ('RELEVANT','NOT_RELEVANT','UNSURE')
  ),
  matcher_version TEXT NOT NULL,
  feedback_context TEXT NOT NULL DEFAULT 'SEARCH_RESULT' CHECK (
    feedback_context IN ('SEARCH_RESULT','GRANT_DETAIL','COMPARISON')
  ),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_relevance_feedback_grant_created
  ON relevance_feedback(grant_call_version_id, created_at DESC);
CREATE INDEX idx_relevance_feedback_matcher_judgment
  ON relevance_feedback(matcher_version, judgment, created_at DESC);
