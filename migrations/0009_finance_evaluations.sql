PRAGMA foreign_keys = ON;

CREATE TABLE finance_evaluations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  funding_scenario_id TEXT REFERENCES funding_scenarios(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (
    status IN (
      'COMPLETE',
      'NEEDS_INFORMATION',
      'SCENARIO_NOT_APPLICABLE',
      'ERROR'
    )
  ),
  currency_code TEXT NOT NULL,
  max_grant_minor INTEGER CHECK (
    max_grant_minor IS NULL OR max_grant_minor >= 0
  ),
  own_eligible_contribution_minor INTEGER CHECK (
    own_eligible_contribution_minor IS NULL
    OR own_eligible_contribution_minor >= 0
  ),
  ineligible_costs_minor INTEGER CHECK (
    ineligible_costs_minor IS NULL OR ineligible_costs_minor >= 0
  ),
  nonrecoverable_vat_minor INTEGER CHECK (
    nonrecoverable_vat_minor IS NULL OR nonrecoverable_vat_minor >= 0
  ),
  minimum_real_cash_requirement_minor INTEGER CHECK (
    minimum_real_cash_requirement_minor IS NULL
    OR minimum_real_cash_requirement_minor >= 0
  ),
  minimum_prefinancing_requirement_minor INTEGER CHECK (
    minimum_prefinancing_requirement_minor IS NULL
    OR minimum_prefinancing_requirement_minor >= 0
  ),
  reason_codes_json TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL,
  evaluated_at TEXT NOT NULL
);

CREATE INDEX idx_finance_project_evaluated
  ON finance_evaluations(project_id, evaluated_at DESC);
CREATE INDEX idx_finance_grant_version
  ON finance_evaluations(grant_call_version_id, evaluated_at DESC);
