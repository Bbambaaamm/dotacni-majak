PRAGMA foreign_keys = ON;

CREATE TABLE grant_evaluation_criteria (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  criterion_type TEXT NOT NULL CHECK (
    criterion_type IN (
      'EXCELLENCE', 'IMPACT', 'QUALITY', 'FEASIBILITY',
      'BUDGET', 'TEAM', 'IMPLEMENTATION', 'SUSTAINABILITY',
      'COMPLIANCE', 'OTHER'
    )
  ),
  necessity TEXT NOT NULL CHECK (
    necessity IN ('REQUIRED', 'CONDITIONAL', 'RECOMMENDED')
  ),
  condition_group_id TEXT REFERENCES rule_groups(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT,
  points_max INTEGER CHECK (points_max IS NULL OR points_max >= 0),
  weight REAL CHECK (weight IS NULL OR weight >= 0),
  threshold REAL CHECK (threshold IS NULL OR threshold >= 0),
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  completeness_status TEXT NOT NULL CHECK (
    completeness_status IN ('COMPLETE', 'PARTIAL', 'UNKNOWN')
  ),
  verification_status TEXT NOT NULL CHECK (
    verification_status IN (
      'AUTO_EXTRACTED', 'PARTIALLY_VERIFIED', 'VERIFIED', 'NEEDS_REVIEW'
    )
  ),
  sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0)
);

CREATE INDEX idx_eval_criteria_version
ON grant_evaluation_criteria(grant_call_version_id, sort_order);

CREATE INDEX idx_eval_criteria_type
ON grant_evaluation_criteria(grant_call_version_id, criterion_type);
