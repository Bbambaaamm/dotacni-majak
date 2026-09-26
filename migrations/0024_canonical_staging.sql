PRAGMA foreign_keys = ON;

CREATE TABLE canonical_staging_items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  source_run_id TEXT REFERENCES source_runs(id) ON DELETE SET NULL,
  ingestion_run_id TEXT REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  external_id TEXT NOT NULL,
  entity_type TEXT NOT NULL CHECK (
    entity_type IN ('GRANT_CALL','PROGRAMME','PROVIDER','DOCUMENT','OTHER')
  ),
  canonical_identity TEXT NOT NULL,
  payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
  content_hash TEXT NOT NULL CHECK (
    length(content_hash) = 64
    AND content_hash = lower(content_hash)
    AND content_hash NOT GLOB '*[^0-9a-f]*'
  ),
  validation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
    validation_status IN ('PENDING','VALID','INVALID','NEEDS_REVIEW')
  ),
  provenance_status TEXT NOT NULL DEFAULT 'MISSING' CHECK (
    provenance_status IN ('COMPLETE','PARTIAL','MISSING')
  ),
  state TEXT NOT NULL DEFAULT 'STAGED' CHECK (
    state IN ('STAGED','READY','REJECTED','PUBLISHED')
  ),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error TEXT,
  published_entity_id TEXT,
  published_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (source_id, external_id, entity_type, content_hash),
  CHECK (
    state <> 'PUBLISHED'
    OR (published_entity_id IS NOT NULL AND published_at IS NOT NULL)
  )
);

CREATE INDEX idx_canonical_staging_source_state
ON canonical_staging_items(source_id, state, updated_at);

CREATE INDEX idx_canonical_staging_identity
ON canonical_staging_items(entity_type, canonical_identity, state);

CREATE INDEX idx_canonical_staging_ready
ON canonical_staging_items(state, validation_status, provenance_status, updated_at);
