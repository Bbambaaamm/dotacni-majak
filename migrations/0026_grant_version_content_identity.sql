PRAGMA foreign_keys = ON;

CREATE UNIQUE INDEX idx_grant_versions_call_content
ON grant_call_versions(grant_call_id, content_hash)
WHERE content_hash IS NOT NULL;
