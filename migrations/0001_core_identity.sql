PRAGMA foreign_keys = ON;

CREATE TABLE providers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  short_name TEXT,
  provider_type TEXT NOT NULL CHECK (provider_type IN ('EU','NATIONAL','REGIONAL','MUNICIPAL','OTHER_PUBLIC')),
  ico TEXT,
  country_code TEXT,
  official_url TEXT
);

CREATE TABLE programmes (
  id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
  code TEXT,
  name TEXT NOT NULL,
  funding_origin TEXT NOT NULL CHECK (funding_origin IN ('CZ_NATIONAL','CZ_REGION','CZ_MUNICIPAL','EU_SHARED','EU_DIRECT','OTHER_PUBLIC')),
  currency_default TEXT,
  valid_from TEXT,
  valid_to TEXT,
  official_url TEXT
);

CREATE INDEX idx_programmes_provider ON programmes(provider_id);

CREATE TABLE grant_calls (
  id TEXT PRIMARY KEY,
  programme_id TEXT NOT NULL REFERENCES programmes(id) ON DELETE RESTRICT,
  canonical_code TEXT,
  canonical_slug TEXT NOT NULL UNIQUE,
  current_version_id TEXT,
  current_status TEXT NOT NULL CHECK (current_status IN ('DRAFT','ANNOUNCED','PLANNED','OPEN','PAUSED','CLOSED','CANCELLED','ARCHIVED')),
  current_title TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  first_published_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_grant_calls_programme ON grant_calls(programme_id);
CREATE INDEX idx_grant_calls_status ON grant_calls(current_status);

CREATE TABLE grant_call_versions (
  id TEXT PRIMARY KEY,
  grant_call_id TEXT NOT NULL REFERENCES grant_calls(id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL CHECK (version_number >= 1),
  captured_at TEXT NOT NULL,
  effective_from TEXT,
  effective_to TEXT,
  title TEXT NOT NULL,
  summary TEXT,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','ANNOUNCED','PLANNED','OPEN','PAUSED','CLOSED','CANCELLED','ARCHIVED')),
  published_at TEXT,
  submission_open_at TEXT,
  submission_close_at TEXT,
  application_url TEXT,
  official_detail_url TEXT,
  currency_code TEXT,
  normalization_version TEXT,
  content_hash TEXT,
  verification_status TEXT NOT NULL CHECK (verification_status IN ('AUTO_EXTRACTED','PARTIALLY_VERIFIED','VERIFIED','NEEDS_REVIEW')),
  created_at TEXT NOT NULL,
  UNIQUE (grant_call_id, version_number)
);

CREATE INDEX idx_versions_call ON grant_call_versions(grant_call_id, version_number DESC);
CREATE INDEX idx_versions_status_deadline ON grant_call_versions(status, submission_close_at);
CREATE INDEX idx_versions_content_hash ON grant_call_versions(content_hash);

CREATE TABLE source_registry (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  adapter_key TEXT NOT NULL,
  authority TEXT NOT NULL CHECK (authority IN ('OFFICIAL','OFFICIAL_OPEN_DATA','SECONDARY')),
  retrieval_mode TEXT NOT NULL,
  refresh_minutes INTEGER NOT NULL CHECK (refresh_minutes > 0),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  priority INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE source_runs (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  records_seen INTEGER NOT NULL DEFAULT 0,
  new_records INTEGER NOT NULL DEFAULT 0,
  changed_records INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  adapter_version TEXT NOT NULL
);

CREATE INDEX idx_source_runs_source_started ON source_runs(source_id, started_at DESC);

CREATE TABLE source_records (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  record_type TEXT NOT NULL,
  grant_call_id TEXT REFERENCES grant_calls(id) ON DELETE SET NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  presence_state TEXT NOT NULL DEFAULT 'SEEN' CHECK (presence_state IN ('SEEN','MISSING_CANDIDATE','CONFIRMED_MISSING')),
  missing_run_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_run_count >= 0),
  content_hash TEXT,
  UNIQUE (source_id, external_id)
);

CREATE INDEX idx_source_records_source_presence ON source_records(source_id, presence_state);
CREATE INDEX idx_source_records_grant_call ON source_records(grant_call_id);
