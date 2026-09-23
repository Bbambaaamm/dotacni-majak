PRAGMA foreign_keys = ON;

CREATE TABLE historical_awards (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE RESTRICT,
  external_id TEXT NOT NULL,
  programme_id TEXT REFERENCES programmes(id) ON DELETE SET NULL,
  provider_id TEXT REFERENCES providers(id) ON DELETE SET NULL,
  recipient_name TEXT NOT NULL,
  recipient_ico TEXT,
  project_title TEXT NOT NULL,
  project_description TEXT,
  grant_amount_minor INTEGER CHECK (grant_amount_minor IS NULL OR grant_amount_minor >= 0),
  total_cost_minor INTEGER CHECK (total_cost_minor IS NULL OR total_cost_minor >= 0),
  currency_code TEXT NOT NULL,
  decision_date TEXT,
  award_year INTEGER CHECK (award_year IS NULL OR (award_year >= 2000 AND award_year <= 2200)),
  location_id TEXT,
  source_url TEXT NOT NULL,
  retrieved_at TEXT,
  UNIQUE (source_id, external_id)
);

CREATE INDEX idx_historical_awards_programme_year
  ON historical_awards(programme_id, award_year DESC);
CREATE INDEX idx_historical_awards_provider_year
  ON historical_awards(provider_id, award_year DESC);
CREATE INDEX idx_historical_awards_recipient_ico
  ON historical_awards(recipient_ico);
CREATE INDEX idx_historical_awards_location_year
  ON historical_awards(location_id, award_year DESC);

CREATE TABLE historical_award_ontology_terms (
  historical_award_id TEXT NOT NULL REFERENCES historical_awards(id) ON DELETE CASCADE,
  ontology_term_code TEXT NOT NULL,
  weight_ppm INTEGER NOT NULL DEFAULT 1000000 CHECK (weight_ppm >= 0 AND weight_ppm <= 1000000),
  PRIMARY KEY (historical_award_id, ontology_term_code)
);

CREATE INDEX idx_historical_award_terms_term
  ON historical_award_ontology_terms(ontology_term_code, historical_award_id);
