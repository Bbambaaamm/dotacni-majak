PRAGMA foreign_keys = ON;

CREATE TABLE applicant_profiles (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  applicant_type TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (
    applicant_type IN (
      'UNKNOWN','NATURAL_PERSON','SELF_EMPLOYED','BUSINESS',
      'MUNICIPALITY','REGION','ASSOCIATION','SPORTS_CLUB',
      'NONPROFIT','SCHOOL','CONTRIBUTORY_ORGANISATION',
      'HOA','COOPERATIVE','AGRICULTURAL_ENTITY',
      'RESEARCH_ORGANISATION','OTHER'
    )
  ),
  ico TEXT CHECK (ico IS NULL OR ico GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
  organisation_name TEXT,
  legal_form_code TEXT,
  municipality_code TEXT,
  municipality_name TEXT,
  region_code TEXT,
  municipality_population INTEGER CHECK (
    municipality_population IS NULL OR municipality_population >= 0
  ),
  municipality_population_as_of TEXT,
  vat_status TEXT CHECK (
    vat_status IS NULL OR vat_status IN ('UNKNOWN','PAYER','NON_PAYER')
  ),
  organisation_size TEXT CHECK (
    organisation_size IS NULL OR
    organisation_size IN ('UNKNOWN','MICRO','SMALL','MEDIUM','LARGE')
  ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_applicant_profiles_ico
ON applicant_profiles(ico)
WHERE ico IS NOT NULL;

CREATE INDEX idx_applicant_profiles_municipality
ON applicant_profiles(municipality_code);

CREATE TABLE applicant_attribute_values (
  id TEXT PRIMARY KEY,
  applicant_profile_id TEXT NOT NULL
    REFERENCES applicant_profiles(id) ON DELETE CASCADE,
  attribute_definition_id TEXT NOT NULL
    REFERENCES attribute_definitions(id) ON DELETE RESTRICT,
  value_json TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (
    source_kind IN ('USER','ARES','CZSO','OTHER_OFFICIAL')
  ),
  source_reference TEXT,
  observed_at TEXT NOT NULL,
  verified_at TEXT,
  UNIQUE (applicant_profile_id, attribute_definition_id)
);

CREATE INDEX idx_applicant_attribute_profile
ON applicant_attribute_values(applicant_profile_id);

INSERT OR IGNORE INTO attribute_definitions(
  id, attribute_key, scope, label_cs, data_type, resolver_key, filterable, indexable
) VALUES
('attr-applicant-type','applicant.type','APPLICANT','Typ žadatele','ENUM',NULL,1,1),
('attr-applicant-ico','applicant.ico','APPLICANT','IČO','STRING','ares.ico',1,1),
('attr-applicant-legal-form','applicant.legal_form','APPLICANT','Právní forma','STRING','ares.legal_form',1,1),
('attr-applicant-municipality-code','applicant.municipality.code','APPLICANT','Kód obce','GEO_ID','ares.municipality_code',1,1),
('attr-applicant-population','applicant.municipality.population','APPLICANT','Počet obyvatel obce','INTEGER','czso.population',1,1),
('attr-applicant-cz-nace','applicant.cz_nace','APPLICANT','CZ-NACE','STRING_SET','ares.cz_nace',1,0),
('attr-applicant-vat-status','applicant.vat_status','APPLICANT','Status DPH','ENUM',NULL,1,0),
('attr-applicant-size','applicant.organisation_size','APPLICANT','Velikost organizace','ENUM',NULL,1,0);
