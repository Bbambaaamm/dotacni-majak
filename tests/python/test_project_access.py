"""Domain tests for dotacni_majak_project_access.

Tests both happy path and error / denied scenarios for the owner capability
service — the Python domain layer that currently has zero test coverage.

These tests use InMemoryProjectAccessRepository, so they are pure unit tests
with no database, no network, and no third-party dependencies.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "project-access" / "src"))

from dotacni_majak_project_access import (
    InMemoryProjectAccessRepository,
    IssuedOwnerCapability,
    OwnerAuditEvent,
    OwnerAuditEventType,
    ProjectOwnerCapability,
    ProjectOwnerCapabilityService,
)


def utc_now(year=2026, month=9, day=28, hour=12, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


class ProjectOwnerCapabilityServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryProjectAccessRepository()
        self.service = ProjectOwnerCapabilityService(self.repo, token_bytes=32)
        self.now = utc_now()

    # ---- issue: creates capability, stores only hash, returns raw token ----

    def test_issue_returns_raw_token_and_stores_only_hash(self):
        issued = self.service.issue("prj_1", now=self.now)
        self.assertIsInstance(issued, IssuedOwnerCapability)
        self.assertEqual(issued.capability.project_id, "prj_1")
        self.assertEqual(issued.capability.generation, 1)
        self.assertIsNone(issued.capability.rotated_at)
        self.assertIsNone(issued.capability.last_used_at)
        self.assertIsNone(issued.capability.revoked_at)
        # server stores only the hash — raw token must not be derivable from repo
        stored = self.repo.get("prj_1")
        self.assertIsNotNone(stored)
        self.assertNotEqual(stored.token_hash, issued.token)
        self.assertTrue(stored.token_hash.isalnum())  # hex digest

    def test_issue_records_audit_event(self):
        self.service.issue("prj_1", now=self.now)
        audit = self.repo.audit
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].project_id, "prj_1")
        self.assertEqual(audit[0].event_type, OwnerAuditEventType.CREATED)

    def test_issue_fails_when_project_already_has_capability(self):
        self.service.issue("prj_1", now=self.now)
        with self.assertRaises(ValueError):
            self.service.issue("prj_1", now=self.now)

    def test_issue_fails_when_token_bytes_too_small(self):
        with self.assertRaises(ValueError):
            ProjectOwnerCapabilityService(self.repo, token_bytes=31)

    # ---- verify: valid token succeeds; invalid / wrong / revoked fails ----

    def test_verify_succeeds_with_valid_token(self):
        issued = self.service.issue("prj_1", now=self.now)
        result = self.service.verify("prj_1", issued.token, now=self.now)
        self.assertTrue(result)

    def test_verify_updates_last_used_at(self):
        issued = self.service.issue("prj_1", now=self.now)
        before = self.repo.get("prj_1").last_used_at
        self.assertIsNone(before)
        self.service.verify("prj_1", issued.token, now=self.now)
        after = self.repo.get("prj_1").last_used_at
        self.assertIsNotNone(after)

    def test_verify_fails_with_invalid_token(self):
        self.service.issue("prj_1", now=self.now)
        result = self.service.verify("prj_1", "not-a-valid-token-xxxxxxxxxxxx", now=self.now)
        self.assertFalse(result)

    def test_verify_fails_for_wrong_project(self):
        issued = self.service.issue("prj_1", now=self.now)
        result = self.service.verify("prj_2", issued.token, now=self.now)
        self.assertFalse(result)

    def test_verify_fails_for_revoked_capability(self):
        issued = self.service.issue("prj_1", now=self.now)
        self.service.revoke("prj_1", issued.token, now=self.now)
        result = self.service.verify("prj_1", issued.token, now=self.now)
        self.assertFalse(result)

    def test_verify_records_denied_audit_for_invalid_token(self):
        self.service.verify("prj_1", "bad-token", now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(e.event_type == OwnerAuditEventType.DENIED_UNKNOWN for e in audit)
        )

    def test_verify_records_denied_audit_for_wrong_project(self):
        issued = self.service.issue("prj_1", now=self.now)
        # verify called with a different project_id — audit records the
        # project_id that was passed to verify (the mismatched one).
        self.service.verify("prj_2", issued.token, now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(
                e.project_id == "prj_2"
                and e.event_type == OwnerAuditEventType.DENIED_PROJECT_MISMATCH
                for e in audit
            )
        )

    def test_verify_records_denied_audit_for_revoked(self):
        issued = self.service.issue("prj_1", now=self.now)
        self.service.revoke("prj_1", issued.token, now=self.now)
        self.service.verify("prj_1", issued.token, now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(
                e.project_id == "prj_1"
                and e.event_type == OwnerAuditEventType.DENIED_REVOKED
                for e in audit
            )
        )

    # ---- rotate: new token, higher generation, old token invalidated ----

    def test_rotate_issues_new_token_and_bumps_generation(self):
        issued = self.service.issue("prj_1", now=self.now)
        rotated = self.service.rotate("prj_1", issued.token, now=self.now)
        self.assertNotEqual(rotated.token, issued.token)
        self.assertEqual(rotated.capability.generation, 2)
        self.assertIsNotNone(rotated.capability.rotated_at)

    def test_old_token_is_invalid_after_rotate(self):
        issued = self.service.issue("prj_1", now=self.now)
        self.service.rotate("prj_1", issued.token, now=self.now)
        result = self.service.verify("prj_1", issued.token, now=self.now)
        self.assertFalse(result)

    def test_newly_rotated_token_is_valid(self):
        issued = self.service.issue("prj_1", now=self.now)
        rotated = self.service.rotate("prj_1", issued.token, now=self.now)
        self.assertTrue(self.service.verify("prj_1", rotated.token, now=self.now))

    def test_rotate_fails_without_valid_token(self):
        self.service.issue("prj_1", now=self.now)
        with self.assertRaises(PermissionError):
            self.service.rotate("prj_1", "bad-token", now=self.now)

    def test_rotate_records_audit_event(self):
        issued = self.service.issue("prj_1", now=self.now)
        self.service.rotate("prj_1", issued.token, now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(e.event_type == OwnerAuditEventType.ROTATED for e in audit)
        )

    # ---- revoke: marks capability revoked ----

    def test_revoke_marks_capability_revoked(self):
        issued = self.service.issue("prj_1", now=self.now)
        result = self.service.revoke("prj_1", issued.token, now=self.now)
        self.assertIsNotNone(result.revoked_at)
        # After revoke, verify must return False (denied).
        self.assertFalse(
            self.service.verify("prj_1", issued.token, now=self.now)
        )
        # Explicit check: capability is revoked in the repository.
        cap = self.repo.get("prj_1")
        self.assertIsNotNone(cap.revoked_at)

    def test_revoke_fails_without_valid_token(self):
        self.service.issue("prj_1", now=self.now)
        with self.assertRaises(PermissionError):
            self.service.revoke("prj_1", "bad-token", now=self.now)

    def test_revoke_records_audit_event(self):
        issued = self.service.issue("prj_1", now=self.now)
        self.service.revoke("prj_1", issued.token, now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(e.event_type == OwnerAuditEventType.REVOKED for e in audit)
        )

    # ---- repository: token hash is the server-side identifier ----

    def test_find_by_hash_returns_capability(self):
        issued = self.service.issue("prj_1", now=self.now)
        found = self.repo.find_by_hash(issued.capability.token_hash)
        self.assertIsNotNone(found)
        self.assertEqual(found.project_id, "prj_1")

    def test_find_by_hash_returns_none_for_unknown_hash(self):
        self.assertIsNone(self.repo.find_by_hash("unknown-hex-hash"))

    def test_repository_preserves_domain_data_contract(self):
        issued = self.service.issue("prj_1", now=self.now)
        cap = self.repo.get("prj_1")
        self.assertEqual(cap.project_id, "prj_1")
        self.assertEqual(cap.generation, 1)
        self.assertTrue(cap.token_hash)
