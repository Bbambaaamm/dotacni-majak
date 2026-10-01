"""Domain tests for dotacni_majak_sharing.

Tests both happy path and error / denied scenarios for the read-only project
sharing service — the Python domain layer that currently has zero test coverage.

These tests use InMemorySharingRepository, so they are pure unit tests with no
database, no network, and no third-party dependencies.
"""
from dataclasses import replace
import secrets
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sharing" / "src"))

from dotacni_majak_sharing.engine import _hash_token
from dotacni_majak_sharing import (
    InMemorySharingRepository,
    IssuedProjectShare,
    ProjectShareLink,
    ProjectSharingService,
    ShareAuditEvent,
    ShareAuditEventType,
    ShareResolution,
    ShareResolutionStatus,
    ShareScope,
)


def utc_now(year=2026, month=9, day=28, hour=12, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


class ProjectSharingServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemorySharingRepository(
            project_owners={"prj_1": "owner_a", "prj_2": "owner_b"}
        )
        self.service = ProjectSharingService(self.repo, default_ttl=timedelta(days=30))
        self.now = utc_now()

    # ---- create: owner can create share, non-owner is denied ----

    def test_create_returns_link_and_raw_token(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        self.assertIsInstance(issued, IssuedProjectShare)
        self.assertIsInstance(issued.link, ProjectShareLink)
        self.assertEqual(issued.link.project_id, "prj_1")
        self.assertEqual(issued.link.owner_user_id, "owner_a")
        self.assertEqual(issued.link.scope, ShareScope.PROJECT_READ_ONLY)
        # raw token is returned once; server stores only hash
        self.assertNotEqual(issued.token, issued.link.token_hash)
        self.assertTrue(issued.link.token_hash.isalnum())  # hex digest

    def test_create_url_path_is_slash_s_token(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        self.assertEqual(issued.url_path, f"/s/{issued.token}")

    def test_create_record_audit_event(self):
        self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        audit = self.repo.audit
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].event_type, ShareAuditEventType.CREATED)
        self.assertEqual(audit[0].project_id, "prj_1")
        self.assertEqual(audit[0].actor_user_id, "owner_a")

    def test_create_fails_when_not_owner(self):
        with self.assertRaises(PermissionError):
            self.service.create(
                project_id="prj_1", owner_user_id="owner_b", now=self.now
            )

    def test_create_records_denied_owner_mismatch_audit(self):
        with self.assertRaises(PermissionError):
            self.service.create(
                project_id="prj_1", owner_user_id="owner_b", now=self.now
            )
        audit = self.repo.audit
        self.assertTrue(
            any(
                e.event_type == ShareAuditEventType.DENIED_OWNER_MISMATCH
                for e in audit
            )
        )

    def test_create_fails_when_token_bytes_too_small(self):
        with self.assertRaises(ValueError):
            ProjectSharingService(self.repo, token_bytes=31)

    def test_create_fails_with_invalid_ttl(self):
        # A ttl that exceeds max_ttl (default 365d) must be rejected.
        with self.assertRaises(ValueError):
            self.service.create(
                project_id="prj_1",
                owner_user_id="owner_a",
                ttl=timedelta(days=400),
                now=self.now,
            )
        # A negative ttl is also rejected (zero ttl falls back to default).
        with self.assertRaises(ValueError):
            self.service.create(
                project_id="prj_1",
                owner_user_id="owner_a",
                ttl=timedelta(days=-1),
                now=self.now,
            )

    def test_create_respects_explicit_ttl(self):
        issued = self.service.create(
            project_id="prj_1",
            owner_user_id="owner_a",
            ttl=timedelta(days=7),
            now=self.now,
        )
        self.assertEqual(issued.link.expires_at, self.now + timedelta(days=7))

    # ---- resolve: valid token grants, revoked/expired/unknown denied ----

    def test_resolve_grants_for_valid_token(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        result = self.service.resolve(issued.token, now=self.now)
        self.assertEqual(result.status, ShareResolutionStatus.GRANTED)
        self.assertEqual(result.project_id, "prj_1")
        self.assertEqual(result.scope, ShareScope.PROJECT_READ_ONLY)

    def test_resolve_updates_last_accessed_at(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        link_before = self.repo.find_by_token_hash(issued.link.token_hash)
        self.assertIsNone(link_before.last_accessed_at)
        self.service.resolve(issued.token, now=self.now)
        link_after = self.repo.find_by_token_hash(issued.link.token_hash)
        self.assertIsNotNone(link_after.last_accessed_at)

    def test_resolve_returns_revoked_for_revoked_link(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="owner_a",
            now=self.now,
        )
        result = self.service.resolve(issued.token, now=self.now)
        self.assertEqual(result.status, ShareResolutionStatus.REVOKED)

    def test_resolve_returns_expired_for_expired_link(self):
        # The service normally creates fresh links; to test expiry we create a link
        # directly with an already-expired expires_at.
        token = secrets.token_urlsafe(32)
        expired_link = ProjectShareLink(
            id="shr_test",
            project_id="prj_1",
            owner_user_id="owner_a",
            token_hash=_hash_token(token),
            scope=ShareScope.PROJECT_READ_ONLY,
            created_at=self.now - timedelta(days=2),
            expires_at=self.now - timedelta(days=1),
        )
        self.repo.create_share(expired_link)
        result = self.service.resolve(token, now=self.now)
        self.assertEqual(result.status, ShareResolutionStatus.EXPIRED)

    def test_resolve_returns_not_found_for_unknown_token(self):
        result = self.service.resolve("completely-unknown-token", now=self.now)
        self.assertEqual(result.status, ShareResolutionStatus.NOT_FOUND)

    def test_resolve_returns_not_found_for_malformed_token(self):
        # token_urlsafe(32) is 43 chars; reject tiny user-controlled strings
        # before any repository lookup.
        result = self.service.resolve("tiny", now=self.now)
        self.assertEqual(result.status, ShareResolutionStatus.NOT_FOUND)

    def test_resolve_denies_revoked_audit(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="owner_a",
            now=self.now,
        )
        self.service.resolve(issued.token, now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(
                e.event_type == ShareAuditEventType.DENIED_REVOKED
                for e in audit
            )
        )

    def test_resolve_denies_expired_audit(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        # Manually expire the link by saving it with a past expires_at.
        expired = replace(
            issued.link,
            expires_at=self.now - timedelta(days=1),
        )
        self.repo.save_share(expired)
        result = self.service.resolve(issued.token, now=self.now)
        self.assertEqual(result.status, ShareResolutionStatus.EXPIRED)
        audit = self.repo.audit
        self.assertTrue(
            any(
                e.event_type == ShareAuditEventType.DENIED_EXPIRED
                for e in audit
            )
        )

    def test_resolve_denies_unknown_token_audit(self):
        self.service.resolve("unknown-token", now=self.now)
        audit = self.repo.audit
        self.assertTrue(
            any(
                e.event_type == ShareAuditEventType.DENIED_UNKNOWN_TOKEN
                for e in audit
            )
        )

    # ---- revoke: owner can revoke, non-owner denied ----

    def test_revoke_marks_link_revoked(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        revoked = self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="owner_a",
            now=self.now,
        )
        self.assertIsNotNone(revoked.revoked_at)

    def test_revoke_fails_when_not_owner(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        with self.assertRaises(PermissionError):
            self.service.revoke(
                share_link_id=issued.link.id,
                owner_user_id="owner_b",
                now=self.now,
            )

    def test_revoke_records_audit_event(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="owner_a",
            now=self.now,
        )
        audit = self.repo.audit
        self.assertTrue(
            any(e.event_type == ShareAuditEventType.REVOKED for e in audit)
        )

    def test_revoke_is_idempotent(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        first = self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="owner_a",
            now=self.now,
        )
        second = self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="owner_a",
            now=self.now,
        )
        self.assertEqual(first.revoked_at, second.revoked_at)

    # ---- repository: token hash is the server-side identifier ----

    def test_find_by_token_hash_returns_link(self):
        issued = self.service.create(
            project_id="prj_1", owner_user_id="owner_a", now=self.now
        )
        found = self.repo.find_by_token_hash(issued.link.token_hash)
        self.assertIsNotNone(found)
        self.assertEqual(found.project_id, "prj_1")

    def test_find_by_token_hash_returns_none_for_unknown(self):
        self.assertIsNone(
            self.repo.find_by_token_hash("deadbeef" + "0" * 56)
        )

    def test_project_owner_lookup(self):
        self.assertEqual(self.repo.project_owner("prj_1"), "owner_a")
        self.assertEqual(self.repo.project_owner("prj_2"), "owner_b")
        self.assertIsNone(self.repo.project_owner("prj_999"))
