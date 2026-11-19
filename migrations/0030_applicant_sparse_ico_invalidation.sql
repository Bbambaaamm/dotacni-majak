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
