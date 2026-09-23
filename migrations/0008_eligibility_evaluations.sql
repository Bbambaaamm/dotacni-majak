PRAGMA foreign_keys = ON;

CREATE TABLE eligibility_evaluations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  applicant_profile_id TEXT NOT NULL
    REFERENCES applicant_profiles(id) ON DELETE CASCADE,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  rule_set_id TEXT NOT NULL
    REFERENCES eligibility_rule_sets(id) ON DELETE RESTRICT,
  result TEXT NOT NULL CHECK (
    result IN (
      'ELIGIBLE','LIKELY_ELIGIBLE','NEEDS_INFORMATION',
      'INELIGIBLE','NEEDS_REVIEW'
    )
  ),
  root_result TEXT NOT NULL CHECK (
    root_result IN ('PASS','FAIL','UNKNOWN','ERROR','NOT_APPLICABLE')
  ),
  rules_total INTEGER NOT NULL DEFAULT 0 CHECK (rules_total >= 0),
  rules_passed INTEGER NOT NULL DEFAULT 0 CHECK (rules_passed >= 0),
  rules_failed INTEGER NOT NULL DEFAULT 0 CHECK (rules_failed >= 0),
  rules_unknown INTEGER NOT NULL DEFAULT 0 CHECK (rules_unknown >= 0),
  engine_version TEXT NOT NULL,
  input_snapshot_hash TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL,
  evaluated_at TEXT NOT NULL
);

CREATE INDEX idx_eligibility_project_evaluated
ON eligibility_evaluations(project_id, evaluated_at DESC);

CREATE INDEX idx_eligibility_grant_result
ON eligibility_evaluations(grant_call_version_id, result);

CREATE TABLE condition_results (
  id TEXT PRIMARY KEY,
  evaluation_id TEXT NOT NULL
    REFERENCES eligibility_evaluations(id) ON DELETE CASCADE,
  rule_condition_id TEXT
    REFERENCES rule_conditions(id) ON DELETE SET NULL,
  attribute_key TEXT NOT NULL,
  actual_value_json TEXT,
  expected_value_json TEXT,
  result TEXT NOT NULL CHECK (
    result IN ('PASS','FAIL','UNKNOWN','ERROR','NOT_APPLICABLE')
  ),
  blocking INTEGER NOT NULL CHECK (blocking IN (0,1)),
  verification_status TEXT NOT NULL CHECK (
    verification_status IN (
      'AUTO_EXTRACTED','PARTIALLY_VERIFIED','VERIFIED','NEEDS_REVIEW'
    )
  ),
  reason_code TEXT NOT NULL
);

CREATE INDEX idx_condition_results_evaluation
ON condition_results(evaluation_id, result);
