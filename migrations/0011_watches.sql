PRAGMA foreign_keys = ON;

CREATE TABLE watches (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  watch_type TEXT NOT NULL CHECK (
    watch_type IN (
      'PROJECT','GRANT','CATEGORY','PROVIDER','GEOGRAPHY','CUSTOM_SEARCH'
    )
  ),
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  grant_call_id TEXT REFERENCES grant_calls(id) ON DELETE CASCADE,
  ontology_term_id TEXT,
  provider_id TEXT REFERENCES providers(id) ON DELETE CASCADE,
  geography_id TEXT,
  filter_json TEXT,
  minimum_match_band TEXT CHECK (
    minimum_match_band IS NULL
    OR minimum_match_band IN ('WEAK','POSSIBLE','VERY_GOOD')
  ),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_watches_project_enabled
  ON watches(project_id, enabled);
CREATE INDEX idx_watches_type_enabled
  ON watches(watch_type, enabled);

CREATE TABLE watch_matches (
  id TEXT PRIMARY KEY,
  watch_id TEXT NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
  project_id TEXT,
  grant_call_id TEXT NOT NULL
    REFERENCES grant_calls(id) ON DELETE CASCADE,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (
    status IN (
      'MATCHED',
      'NEEDS_INFORMATION',
      'NEEDS_REVIEW',
      'NOT_ELIGIBLE',
      'NOT_FINANCIALLY_COMPATIBLE',
      'NOT_RELEVANT'
    )
  ),
  match_band TEXT NOT NULL CHECK (
    match_band IN ('WEAK','POSSIBLE','VERY_GOOD')
  ),
  relevance_score_ppm INTEGER NOT NULL CHECK (
    relevance_score_ppm >= 0 AND relevance_score_ppm <= 1000000
  ),
  reason_codes_json TEXT NOT NULL,
  notification_candidate INTEGER NOT NULL CHECK (
    notification_candidate IN (0,1)
  ),
  dedupe_key TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_watch_matches_watch_updated
  ON watch_matches(watch_id, updated_at DESC);
CREATE INDEX idx_watch_matches_call_version
  ON watch_matches(grant_call_id, grant_call_version_id);
CREATE INDEX idx_watch_matches_notification
  ON watch_matches(notification_candidate, status, updated_at DESC);
