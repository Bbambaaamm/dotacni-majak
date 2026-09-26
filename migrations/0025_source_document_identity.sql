PRAGMA foreign_keys = ON;

CREATE UNIQUE INDEX idx_source_documents_identity
ON source_documents(source_id, document_type, source_url);
