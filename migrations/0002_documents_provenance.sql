PRAGMA foreign_keys = ON;

CREATE TABLE source_documents (
  id TEXT PRIMARY KEY,
  grant_call_id TEXT REFERENCES grant_calls(id) ON DELETE SET NULL,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE RESTRICT,
  document_type TEXT NOT NULL CHECK (document_type IN ('CALL_DOCUMENT','GUIDELINES','ANNEX','APPLICATION_FORM','FAQ','PROGRAMME_DOCUMENT','OTHER')),
  title TEXT,
  source_url TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT
);

CREATE INDEX idx_documents_grant_call ON source_documents(grant_call_id);
CREATE INDEX idx_documents_source ON source_documents(source_id);

CREATE TABLE document_versions (
  id TEXT PRIMARY KEY,
  source_document_id TEXT NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
  sha256 TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size INTEGER CHECK (file_size IS NULL OR file_size >= 0),
  object_key TEXT NOT NULL,
  parser_version TEXT,
  extraction_status TEXT NOT NULL CHECK (extraction_status IN ('PENDING','EXTRACTED','FAILED','QUARANTINED')),
  page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
  language_code TEXT,
  UNIQUE (source_document_id, sha256)
);

CREATE INDEX idx_document_versions_document ON document_versions(source_document_id, retrieved_at DESC);
CREATE INDEX idx_document_versions_sha ON document_versions(sha256);

CREATE TABLE document_sections (
  id TEXT PRIMARY KEY,
  document_version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  heading TEXT,
  section_path TEXT,
  page_from INTEGER,
  page_to INTEGER,
  char_start INTEGER,
  char_end INTEGER,
  text_content TEXT NOT NULL,
  section_type TEXT
);

CREATE INDEX idx_sections_document ON document_sections(document_version_id);
CREATE INDEX idx_sections_pages ON document_sections(document_version_id, page_from, page_to);

CREATE TABLE field_evidence (
  id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  field_path TEXT NOT NULL,
  document_version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
  document_section_id TEXT REFERENCES document_sections(id) ON DELETE SET NULL,
  page_from INTEGER,
  page_to INTEGER,
  evidence_text TEXT,
  extraction_method TEXT,
  extractor_version TEXT,
  confidence_ppm INTEGER CHECK (confidence_ppm IS NULL OR (confidence_ppm >= 0 AND confidence_ppm <= 1000000)),
  verification_status TEXT NOT NULL CHECK (verification_status IN ('AUTO_EXTRACTED','PARTIALLY_VERIFIED','VERIFIED','NEEDS_REVIEW')),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_evidence_entity_field ON field_evidence(entity_type, entity_id, field_path);
CREATE INDEX idx_evidence_document ON field_evidence(document_version_id);
