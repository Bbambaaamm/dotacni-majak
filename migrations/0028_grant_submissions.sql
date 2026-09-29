PRAGMA foreign_keys = ON;

-- GrantSubmission models the practical, version-specific information a
-- candidate needs to actually submit an application: the submission portal
-- URL, the application method, account/signature requirements, and the
-- provider's public contact details.
--
-- Unlike the legacy `application_url` column on grant_call_versions (which is
-- not surfaced in the v1 canonical schema), GrantSubmission carries per-field
-- provenance (evidence_id) and completeness/verification status so every claim
-- is accountable and the UI never presents a user-supplied guess as official
-- fact. One submission block per version (1:1); absence of a row == UNKNOWN.

CREATE TABLE grant_submissions (
  id TEXT PRIMARY KEY,
  grant_call_version_id TEXT NOT NULL
    REFERENCES grant_call_versions(id) ON DELETE CASCADE,
  portal_url TEXT,
  application_method TEXT CHECK (
    application_method IN ('ELECTRONIC','PAPER','HYBRID','EMAIL','POSTAL','OTHER')
  ),
  account_requirement TEXT,
  signature_requirement TEXT,
  contact_name TEXT,
  contact_role TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  evidence_id TEXT REFERENCES field_evidence(id) ON DELETE SET NULL,
  completeness_status TEXT NOT NULL CHECK (
    completeness_status IN ('COMPLETE','PARTIAL','UNKNOWN')
  ),
  verification_status TEXT NOT NULL CHECK (
    verification_status IN ('AUTO_EXTRACTED','PARTIALLY_VERIFIED','VERIFIED','NEEDS_REVIEW')
  ),
  UNIQUE (grant_call_version_id)
);

CREATE INDEX idx_grant_submissions_version
ON grant_submissions(grant_call_version_id);

CREATE INDEX idx_grant_submissions_evidence
ON grant_submissions(evidence_id)
WHERE evidence_id IS NOT NULL;
