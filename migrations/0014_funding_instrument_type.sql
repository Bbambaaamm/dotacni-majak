PRAGMA foreign_keys = ON;

ALTER TABLE grant_call_versions
  ADD COLUMN funding_instrument_type TEXT NOT NULL DEFAULT 'GRANT'
  CHECK (funding_instrument_type IN ('GRANT','LOAN','GUARANTEE','EQUITY','MIXED','OTHER'));

ALTER TABLE funding_scenarios
  ADD COLUMN instrument_type TEXT NOT NULL DEFAULT 'GRANT'
  CHECK (instrument_type IN ('GRANT','LOAN','GUARANTEE','EQUITY','MIXED','OTHER'));

CREATE INDEX idx_versions_instrument_status
  ON grant_call_versions(funding_instrument_type, status);

CREATE INDEX idx_funding_instrument
  ON funding_scenarios(instrument_type, grant_call_version_id);
