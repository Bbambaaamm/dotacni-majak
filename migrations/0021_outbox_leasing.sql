PRAGMA foreign_keys = ON;

ALTER TABLE outbox_events ADD COLUMN lease_owner TEXT;
ALTER TABLE outbox_events ADD COLUMN lease_expires_at TEXT;
ALTER TABLE outbox_events ADD COLUMN dead_lettered_at TEXT;

CREATE INDEX idx_outbox_claimable
  ON outbox_events(dead_lettered_at, status, available_at, lease_expires_at);
