PRAGMA foreign_keys = ON;

CREATE TABLE notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  watch_id TEXT REFERENCES watches(id) ON DELETE SET NULL,
  grant_call_version_id TEXT
    REFERENCES grant_call_versions(id) ON DELETE SET NULL,
  change_event_id TEXT REFERENCES change_events(id) ON DELETE SET NULL,
  notification_type TEXT NOT NULL CHECK (
    notification_type IN (
      'NEW_MATCHING_GRANT',
      'MATCH_NEEDS_INFORMATION',
      'GRANT_CHANGED',
      'DEADLINE_REMINDER'
    )
  ),
  channel TEXT NOT NULL CHECK (channel IN ('IN_APP','WEB_PUSH')),
  severity TEXT NOT NULL CHECK (
    severity IN ('INFO','IMPORTANT','CRITICAL')
  ),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (
    status IN ('PENDING','SENT','READ','FAILED','SUPPRESSED')
  ),
  created_at TEXT NOT NULL,
  sent_at TEXT,
  read_at TEXT,
  last_error TEXT
);

CREATE INDEX idx_notifications_user_status
  ON notifications(user_id, status, created_at DESC);
CREATE INDEX idx_notifications_watch
  ON notifications(watch_id, created_at DESC);

CREATE TABLE web_push_subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  endpoint_ciphertext TEXT NOT NULL,
  p256dh_ciphertext TEXT NOT NULL,
  auth_ciphertext TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  opt_in_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_push_subscriptions_user_active
  ON web_push_subscriptions(user_id, active);
