PRAGMA foreign_keys = ON;

CREATE TABLE attribute_definitions (
  id TEXT PRIMARY KEY,
  attribute_key TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL CHECK (scope IN ('APPLICANT','PROJECT')),
  label_cs TEXT NOT NULL,
  data_type TEXT NOT NULL CHECK (
    data_type IN (
      'STRING','INTEGER','NUMBER','BOOLEAN','DATE','DATETIME',
      'MONEY_MINOR','PERCENT_BPS','ENUM','GEO_ID','STRING_SET'
    )
  ),
  unit TEXT,
  resolver_key TEXT,
  enum_values_json TEXT,
  filterable INTEGER NOT NULL DEFAULT 0 CHECK (filterable IN (0,1)),
  indexable INTEGER NOT NULL DEFAULT 0 CHECK (indexable IN (0,1)),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  CHECK (
    (scope = 'APPLICANT' AND attribute_key LIKE 'applicant.%')
    OR
    (scope = 'PROJECT' AND attribute_key LIKE 'project.%')
  )
);

CREATE INDEX idx_attribute_definitions_scope_active
ON attribute_definitions(scope, active);

CREATE TABLE eligibility_rule_sets (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  completeness_status TEXT NOT NULL CHECK (
    completeness_status IN ('COMPLETE','PARTIAL','UNKNOWN')
  ),
  verification_status TEXT NOT NULL CHECK (
    verification_status IN (
      'AUTO_EXTRACTED','PARTIALLY_VERIFIED','VERIFIED','NEEDS_REVIEW'
    )
  )
);

CREATE INDEX idx_rule_sets_version
ON eligibility_rule_sets(grant_call_version_id);

CREATE TABLE rule_groups (
  id TEXT PRIMARY KEY,
  rule_set_id TEXT NOT NULL
    REFERENCES eligibility_rule_sets(id) ON DELETE CASCADE,
  parent_group_id TEXT REFERENCES rule_groups(id) ON DELETE CASCADE,
  group_operator TEXT NOT NULL CHECK (group_operator IN ('AND','OR','NOT')),
  sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  CHECK (parent_group_id IS NULL OR parent_group_id <> id)
);

-- A rule set must have at most one root. Runtime validation requires exactly one.
CREATE UNIQUE INDEX idx_rule_groups_single_root
ON rule_groups(rule_set_id)
WHERE parent_group_id IS NULL;

CREATE INDEX idx_rule_groups_parent
ON rule_groups(rule_set_id, parent_group_id, sort_order);

CREATE TABLE rule_conditions (
  id TEXT PRIMARY KEY,
  rule_group_id TEXT NOT NULL REFERENCES rule_groups(id) ON DELETE CASCADE,
  attribute_definition_id TEXT NOT NULL
    REFERENCES attribute_definitions(id) ON DELETE RESTRICT,
  condition_operator TEXT NOT NULL CHECK (
    condition_operator IN (
      'EQ','NEQ','IN','NOT_IN','LT','LTE','GT','GTE','BETWEEN',
      'EXISTS','NOT_EXISTS','CONTAINS','INTERSECTS',
      'DATE_BEFORE','DATE_AFTER','GEO_WITHIN','GEO_NOT_WITHIN'
    )
  ),
  expected_value_json TEXT NOT NULL DEFAULT 'null',
  blocking INTEGER NOT NULL DEFAULT 1 CHECK (blocking IN (0,1)),
  unknown_policy TEXT NOT NULL DEFAULT 'PROPAGATE' CHECK (
    unknown_policy IN ('PROPAGATE','NOT_APPLICABLE')
  ),
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  confidence_ppm INTEGER CHECK (
    confidence_ppm IS NULL OR
    (confidence_ppm >= 0 AND confidence_ppm <= 1000000)
  ),
  verification_status TEXT NOT NULL CHECK (
    verification_status IN (
      'AUTO_EXTRACTED','PARTIALLY_VERIFIED','VERIFIED','NEEDS_REVIEW'
    )
  ),
  sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0)
);

CREATE INDEX idx_rule_conditions_group
ON rule_conditions(rule_group_id, sort_order);

CREATE INDEX idx_rule_conditions_attribute
ON rule_conditions(attribute_definition_id);
