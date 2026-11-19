-- Existing duplicate non-null user_id values must be reconciled before this
-- migration. The unique index deliberately fails instead of discarding data.
CREATE UNIQUE INDEX IF NOT EXISTS idx_applicant_profiles_user_id ON applicant_profiles(user_id)
WHERE user_id IS NOT NULL;
-- Convert legacy token-hash keys only when a live capability identifies the
-- project. A conflicting owner mapping fails atomically; no row is discarded.
UPDATE applicant_profiles
SET user_id = (
  SELECT p.owner_user_id
  FROM project_owner_capabilities AS c
  JOIN projects AS p ON p.id = c.project_id
  WHERE applicant_profiles.user_id = 'anonymous:' || c.token_hash
    AND c.revoked_at IS NULL
    AND p.owner_user_id IS NOT NULL
)
WHERE user_id IN (
  SELECT 'anonymous:' || c.token_hash
  FROM project_owner_capabilities AS c
  JOIN projects AS p ON p.id = c.project_id
  WHERE c.revoked_at IS NULL AND p.owner_user_id IS NOT NULL
);
DROP INDEX IF EXISTS idx_applicant_profiles_ico;
CREATE INDEX idx_applicant_profiles_ico ON applicant_profiles(ico) WHERE ico IS NOT NULL;
