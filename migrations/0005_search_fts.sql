PRAGMA foreign_keys = ON;

CREATE TABLE grant_search_documents (
  grant_call_version_id TEXT PRIMARY KEY
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  supported_activities TEXT NOT NULL DEFAULT '',
  eligible_costs TEXT NOT NULL DEFAULT '',
  keywords TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (
    status IN ('DRAFT','ANNOUNCED','PLANNED','OPEN','PAUSED','CLOSED','CANCELLED','ARCHIVED')
  ),
  submission_close_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_search_documents_status_deadline
  ON grant_search_documents(status, submission_close_at);

CREATE VIRTUAL TABLE grant_search_fts USING fts5(
  grant_call_version_id UNINDEXED,
  title,
  summary,
  supported_activities,
  eligible_costs,
  keywords,
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER grant_search_documents_ai
AFTER INSERT ON grant_search_documents
BEGIN
  INSERT INTO grant_search_fts(
    grant_call_version_id,
    title,
    summary,
    supported_activities,
    eligible_costs,
    keywords
  ) VALUES (
    new.grant_call_version_id,
    new.title,
    new.summary,
    new.supported_activities,
    new.eligible_costs,
    new.keywords
  );
END;

CREATE TRIGGER grant_search_documents_au
AFTER UPDATE ON grant_search_documents
BEGIN
  DELETE FROM grant_search_fts
    WHERE grant_call_version_id = old.grant_call_version_id;
  INSERT INTO grant_search_fts(
    grant_call_version_id,
    title,
    summary,
    supported_activities,
    eligible_costs,
    keywords
  ) VALUES (
    new.grant_call_version_id,
    new.title,
    new.summary,
    new.supported_activities,
    new.eligible_costs,
    new.keywords
  );
END;

CREATE TRIGGER grant_search_documents_ad
AFTER DELETE ON grant_search_documents
BEGIN
  DELETE FROM grant_search_fts
    WHERE grant_call_version_id = old.grant_call_version_id;
END;
