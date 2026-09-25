PRAGMA foreign_keys = ON;

-- Canonical geography hierarchy.
CREATE TABLE geographies (
  id TEXT PRIMARY KEY,
  geography_type TEXT NOT NULL CHECK (
    geography_type IN (
      'COUNTRY','NUTS2','NUTS3','REGION','DISTRICT',
      'ORP','MUNICIPALITY','MAS','OTHER'
    )
  ),
  name TEXT NOT NULL,
  parent_id TEXT REFERENCES geographies(id) ON DELETE RESTRICT,
  country_code TEXT NOT NULL CHECK (
    length(country_code) = 2 AND country_code = upper(country_code)
  ),
  code TEXT,
  nuts_code TEXT,
  lau_code TEXT,
  orp_code TEXT,
  mas_code TEXT,
  valid_from TEXT,
  valid_to TEXT,
  CHECK (parent_id IS NULL OR parent_id <> id),
  CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to)
);

CREATE INDEX idx_geographies_parent
ON geographies(parent_id, geography_type, name);

CREATE INDEX idx_geographies_type_country
ON geographies(geography_type, country_code, name);

CREATE UNIQUE INDEX idx_geographies_nuts
ON geographies(nuts_code)
WHERE nuts_code IS NOT NULL;

CREATE UNIQUE INDEX idx_geographies_lau
ON geographies(lau_code)
WHERE lau_code IS NOT NULL;

CREATE UNIQUE INDEX idx_geographies_orp
ON geographies(orp_code)
WHERE orp_code IS NOT NULL;

CREATE UNIQUE INDEX idx_geographies_mas
ON geographies(mas_code)
WHERE mas_code IS NOT NULL;

CREATE TABLE grant_geographies (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  geography_id TEXT NOT NULL
    REFERENCES geographies(id) ON DELETE RESTRICT,
  mode TEXT NOT NULL CHECK (mode IN ('INCLUDE','EXCLUDE')),
  applies_to TEXT NOT NULL CHECK (
    applies_to IN ('PROJECT_LOCATION','APPLICANT_SEAT','BOTH')
  ),
  include_descendants INTEGER NOT NULL DEFAULT 1 CHECK (
    include_descendants IN (0,1)
  ),
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  UNIQUE (
    grant_call_version_id,
    geography_id,
    mode,
    applies_to
  )
);

CREATE INDEX idx_grant_geographies_version
ON grant_geographies(grant_call_version_id, applies_to, mode);

CREATE INDEX idx_grant_geographies_geography
ON grant_geographies(geography_id, applies_to);

-- Normalized hierarchy for applicant types. Existing applicant_type enum stays
-- in applicant_profiles for canonical-v1/runtime compatibility.
CREATE TABLE applicant_types (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE CHECK (
    code GLOB '[A-Z]*' AND code NOT GLOB '*[^A-Z0-9_]*'
  ),
  name_cs TEXT NOT NULL,
  parent_id TEXT REFERENCES applicant_types(id) ON DELETE RESTRICT,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  sort_order INTEGER CHECK (sort_order IS NULL OR sort_order >= 0),
  CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE INDEX idx_applicant_types_parent
ON applicant_types(parent_id, active, sort_order);

ALTER TABLE applicant_profiles
ADD COLUMN applicant_type_id TEXT REFERENCES applicant_types(id) ON DELETE RESTRICT;

ALTER TABLE applicant_profiles
ADD COLUMN seat_geography_id TEXT REFERENCES geographies(id) ON DELETE RESTRICT;

ALTER TABLE applicant_profiles
ADD COLUMN public_private_status TEXT CHECK (
  public_private_status IS NULL OR
  public_private_status IN ('PUBLIC','PRIVATE','MIXED','UNKNOWN')
);

ALTER TABLE applicant_profiles
ADD COLUMN nonprofit_status TEXT CHECK (
  nonprofit_status IS NULL OR
  nonprofit_status IN ('NONPROFIT','FOR_PROFIT','UNKNOWN')
);

ALTER TABLE applicant_profiles
ADD COLUMN cz_nace_json TEXT NOT NULL DEFAULT '[]'
CHECK (json_valid(cz_nace_json));

ALTER TABLE applicant_profiles
ADD COLUMN field_sources_json TEXT NOT NULL DEFAULT '{}'
CHECK (json_valid(field_sources_json));

CREATE INDEX idx_applicant_profiles_type_id
ON applicant_profiles(applicant_type_id);

CREATE INDEX idx_applicant_profiles_seat_geo
ON applicant_profiles(seat_geography_id);

-- Rebuild dynamic values to add explicit value type, provenance status and
-- evidence while preserving all legacy rows.
ALTER TABLE applicant_attribute_values
RENAME TO applicant_attribute_values_legacy;

CREATE TABLE applicant_attribute_values (
  id TEXT PRIMARY KEY,
  applicant_profile_id TEXT NOT NULL
    REFERENCES applicant_profiles(id) ON DELETE CASCADE,
  attribute_definition_id TEXT NOT NULL
    REFERENCES attribute_definitions(id) ON DELETE RESTRICT,
  value_type TEXT NOT NULL CHECK (
    value_type IN (
      'STRING','INTEGER','NUMBER','BOOLEAN','DATE','DATETIME',
      'MONEY_MINOR','PERCENT_BPS','ENUM','GEO_ID','STRING_SET'
    )
  ),
  value_json TEXT NOT NULL CHECK (json_valid(value_json)),
  source_kind TEXT NOT NULL CHECK (
    source_kind IN ('USER','ARES','CZSO','OTHER_OFFICIAL','DERIVED')
  ),
  source_reference TEXT,
  observed_at TEXT NOT NULL,
  verified_at TEXT,
  verification_status TEXT NOT NULL CHECK (
    verification_status IN (
      'USER_DECLARED','AUTO_EXTRACTED','PARTIALLY_VERIFIED',
      'VERIFIED','NEEDS_REVIEW'
    )
  ),
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  UNIQUE (applicant_profile_id, attribute_definition_id)
);

INSERT INTO applicant_attribute_values(
  id,
  applicant_profile_id,
  attribute_definition_id,
  value_type,
  value_json,
  source_kind,
  source_reference,
  observed_at,
  verified_at,
  verification_status,
  evidence_id
)
SELECT
  id,
  applicant_profile_id,
  attribute_definition_id,
  CASE
    WHEN json_valid(value_json) = 0 THEN 'STRING'
    WHEN json_type(value_json) = 'integer' THEN 'INTEGER'
    WHEN json_type(value_json) = 'real' THEN 'NUMBER'
    WHEN json_type(value_json) IN ('true','false') THEN 'BOOLEAN'
    WHEN json_type(value_json) = 'array' THEN 'STRING_SET'
    ELSE 'STRING'
  END,
  CASE
    WHEN json_valid(value_json) = 1 THEN value_json
    ELSE json_quote(value_json)
  END,
  source_kind,
  source_reference,
  observed_at,
  verified_at,
  CASE
    WHEN verified_at IS NOT NULL THEN 'VERIFIED'
    WHEN source_kind = 'USER' THEN 'USER_DECLARED'
    ELSE 'NEEDS_REVIEW'
  END,
  NULL
FROM applicant_attribute_values_legacy;

DROP TABLE applicant_attribute_values_legacy;

CREATE INDEX idx_applicant_attribute_profile
ON applicant_attribute_values(applicant_profile_id);

CREATE INDEX idx_applicant_attribute_definition
ON applicant_attribute_values(attribute_definition_id, verification_status);

CREATE INDEX idx_applicant_attribute_source
ON applicant_attribute_values(source_kind, observed_at);
