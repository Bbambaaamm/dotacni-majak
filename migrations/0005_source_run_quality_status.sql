PRAGMA foreign_keys = ON;

ALTER TABLE source_runs ADD COLUMN quality_status TEXT NOT NULL DEFAULT 'HEALTHY'
  CHECK (quality_status IN ('HEALTHY','DEGRADED'));

ALTER TABLE source_runs ADD COLUMN destructive_changes_allowed INTEGER NOT NULL DEFAULT 1
  CHECK (destructive_changes_allowed IN (0,1));
