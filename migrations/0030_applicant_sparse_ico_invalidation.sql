-- Sparse facts may describe the previous organisation. Invalidate their
-- verification in the same statement that changes the owner's IČO.
CREATE TRIGGER applicant_sparse_ico_invalidation
AFTER UPDATE OF ico ON applicant_profiles
WHEN OLD.ico IS NOT NEW.ico
BEGIN
  UPDATE applicant_attribute_values
  SET verification_status = CASE WHEN source_kind = 'USER' THEN 'USER_DECLARED' ELSE 'NEEDS_REVIEW' END,
      verified_at = NULL
  WHERE applicant_profile_id = NEW.id;
END;

-- Municipality-dependent sparse facts cannot retain verification after an
-- owner changes municipality, even when their IČO stays the same.
CREATE TRIGGER applicant_sparse_municipality_invalidation
AFTER UPDATE OF municipality_code ON applicant_profiles
WHEN OLD.municipality_code IS NOT NEW.municipality_code
BEGIN
  UPDATE applicant_attribute_values
  SET verification_status = CASE WHEN source_kind = 'USER' THEN 'USER_DECLARED' ELSE 'NEEDS_REVIEW' END,
      verified_at = NULL
  WHERE applicant_profile_id = NEW.id
    AND attribute_definition_id IN (
      SELECT id FROM attribute_definitions WHERE attribute_key LIKE 'applicant.municipality.%'
    );
END;
