PRAGMA foreign_keys = ON;

-- Project indicators: structured, code/name/unit indicators for a GrantCallVersion
-- where the source publishes a known structure (e.g. KPI tables, indicator lists).
--
-- Indicators are immutable per version and follow the same provenance / necessity /
-- completeness rules as grant_requirements and grant_evaluation_criteria:
--  - REQUIRED / CONDITIONAL / RECOMMENDED preserves conditional semantics.
--  - UNKNOWN != FAIL: missing target values mean UNKNOWN, not automatic rejection.
--  - No probability/chance/score fields — indicators are official facts, not "chances".
--  - Every critical claim carries evidenceId or completenessStatus = UNKNOWN.

CREATE TABLE grant_project_indicators (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,

  -- Official indicator identity from the funding source.
  indicator_code TEXT NOT NULL,   -- e.g. "CO2_REDUCTION", "JOB_CREATE", "IPARD_M1"
  indicator_name TEXT NOT NULL,   -- Human label as published
  indicator_unit TEXT,            -- e.g. "t CO2-eq", "M EUR", "jm", "%", null when not published
  indicator_category TEXT,        -- Optional grouping: ENVIRONMENTAL, ECONOMIC, SOCIAL, DIGITAL, OTHER

  -- Applicability / conditional semantics (same as grant_requirements/evaluation_criteria).
  necessity TEXT NOT NULL CHECK (
    necessity IN ('REQUIRED', 'CONDITIONAL', 'RECOMMENDED')
  ),
  condition_group_id TEXT REFERENCES rule_groups(id) ON DELETE SET NULL,

  -- Target rules: baseline + target value with direction and period.
  -- NULLs mean "source does not publish this value" (UNKNOWN), not failure.
  baseline TEXT,                  -- Baseline figure as published, e.g. "120 t CO2-eq/rok"
  target_value REAL,             -- Numeric target when source publishes a number; null otherwise
  target_direction TEXT CHECK (
    target_direction IS NULL OR target_direction IN ('INCREASE', 'DECREASE', 'REACH', 'MAINTAIN')
  ),
  target_period_type TEXT CHECK (
    target_period_type IS NULL
    OR target_period_type IN ('PER_PROJECT', 'PER_YEAR', 'PER_MONTH', 'ONCE')
  ),

  -- Provenance / verification (same contract as other critical-field tables).
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

CREATE INDEX idx_indicators_version
  ON grant_project_indicators(grant_call_version_id, sort_order);
CREATE INDEX idx_indicators_code
  ON grant_project_indicators(grant_call_version_id, indicator_code);
CREATE INDEX idx_indicators_necessity
  ON grant_project_indicators(grant_call_version_id, necessity);
