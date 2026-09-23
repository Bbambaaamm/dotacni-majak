PRAGMA foreign_keys = ON;

CREATE TABLE grant_deadlines (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  deadline_type TEXT NOT NULL CHECK (deadline_type IN ('APPLICATION_OPEN','APPLICATION_CLOSE','PROJECT_START','PROJECT_FINISH','DOCUMENT_COMPLETION','SUSTAINABILITY_END','OTHER')),
  starts_at TEXT,
  ends_at TEXT,
  timezone TEXT,
  description TEXT,
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL
);

CREATE INDEX idx_deadlines_version_type ON grant_deadlines(grant_call_version_id, deadline_type);
CREATE INDEX idx_deadlines_end ON grant_deadlines(ends_at);

CREATE TABLE funding_scenarios (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  condition_group_id TEXT,
  currency_code TEXT NOT NULL,
  support_rate_min_bps INTEGER CHECK (support_rate_min_bps IS NULL OR (support_rate_min_bps >= 0 AND support_rate_min_bps <= 10000)),
  support_rate_max_bps INTEGER CHECK (support_rate_max_bps IS NULL OR (support_rate_max_bps >= 0 AND support_rate_max_bps <= 10000)),
  grant_amount_min_minor INTEGER CHECK (grant_amount_min_minor IS NULL OR grant_amount_min_minor >= 0),
  grant_amount_max_minor INTEGER CHECK (grant_amount_max_minor IS NULL OR grant_amount_max_minor >= 0),
  project_cost_min_minor INTEGER CHECK (project_cost_min_minor IS NULL OR project_cost_min_minor >= 0),
  project_cost_max_minor INTEGER CHECK (project_cost_max_minor IS NULL OR project_cost_max_minor >= 0),
  payment_mode TEXT,
  vat_rule TEXT,
  advance_payment_allowed INTEGER CHECK (advance_payment_allowed IS NULL OR advance_payment_allowed IN (0,1)),
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  CHECK (support_rate_min_bps IS NULL OR support_rate_max_bps IS NULL OR support_rate_min_bps <= support_rate_max_bps),
  CHECK (grant_amount_min_minor IS NULL OR grant_amount_max_minor IS NULL OR grant_amount_min_minor <= grant_amount_max_minor),
  CHECK (project_cost_min_minor IS NULL OR project_cost_max_minor IS NULL OR project_cost_min_minor <= project_cost_max_minor)
);

CREATE INDEX idx_funding_version ON funding_scenarios(grant_call_version_id);

CREATE TABLE grant_requirements (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  requirement_type TEXT NOT NULL CHECK (requirement_type IN ('DOCUMENT','ACTION','PERMIT','DECLARATION','REGISTRATION','APPROVAL','OTHER')),
  title TEXT NOT NULL,
  description TEXT,
  necessity TEXT NOT NULL CHECK (necessity IN ('REQUIRED','CONDITIONAL','RECOMMENDED')),
  condition_group_id TEXT,
  phase TEXT,
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL
);

CREATE INDEX idx_requirements_version ON grant_requirements(grant_call_version_id, necessity);

CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  applicant_profile_id TEXT,
  title TEXT,
  natural_language_intent TEXT NOT NULL,
  location_id TEXT,
  estimated_total_budget_minor INTEGER CHECK (estimated_total_budget_minor IS NULL OR estimated_total_budget_minor >= 0),
  currency_code TEXT NOT NULL,
  desired_grant_amount_minor INTEGER CHECK (desired_grant_amount_minor IS NULL OR desired_grant_amount_minor >= 0),
  max_own_contribution_bps INTEGER CHECK (max_own_contribution_bps IS NULL OR (max_own_contribution_bps >= 0 AND max_own_contribution_bps <= 10000)),
  max_own_contribution_amount_minor INTEGER CHECK (max_own_contribution_amount_minor IS NULL OR max_own_contribution_amount_minor >= 0),
  planned_start TEXT,
  planned_end TEXT,
  investment_type TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_projects_updated ON projects(updated_at DESC);

CREATE TABLE change_events (
  id TEXT PRIMARY KEY,
  grant_call_id TEXT NOT NULL REFERENCES grant_calls(id) ON DELETE CASCADE,
  from_version_id TEXT NOT NULL REFERENCES grant_call_versions(id) ON DELETE RESTRICT,
  to_version_id TEXT NOT NULL REFERENCES grant_call_versions(id) ON DELETE RESTRICT,
  change_type TEXT NOT NULL CHECK (change_type IN ('DEADLINE_CHANGED','STATUS_CHANGED','APPLICANT_RULE_CHANGED','FUNDING_CHANGED','BUDGET_CHANGED','SUPPORTED_ACTIVITY_CHANGED','REQUIREMENT_CHANGED','DOCUMENT_CHANGED','OTHER')),
  severity TEXT NOT NULL CHECK (severity IN ('CRITICAL','IMPORTANT','INFORMATIONAL','EDITORIAL')),
  field_path TEXT,
  old_value_json TEXT,
  new_value_json TEXT,
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  CHECK (from_version_id <> to_version_id)
);

CREATE INDEX idx_change_call_created ON change_events(grant_call_id, created_at DESC);
CREATE INDEX idx_change_severity_created ON change_events(severity, created_at DESC);
