import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sharing" / "src"))

from dotacni_majak_sharing import (
    InMemorySharingRepository,
    ProjectSharingService,
    ShareAuditEventType,
    ShareResolutionStatus,
)


NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


class ProjectSharingServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemorySharingRepository(project_owners={"p1": "u1"})
        self.service = ProjectSharingService(self.repo)

    def test_issue_stores_only_hash_and_returns_high_entropy_token_once(self):
        issued = self.service.create(
            project_id="p1",
            owner_user_id="u1",
            now=NOW,
        )
        self.assertGreaterEqual(len(issued.token), 40)
        self.assertEqual(issued.url_path, f"/s/{issued.token}")
        self.assertNotEqual(issued.link.token_hash, issued.token)
        self.assertNotIn(issued.token, repr(issued.link))
        self.assertEqual(
            self.repo.audit[-1].event_type,
            ShareAuditEventType.CREATED,
        )

    def test_owner_mismatch_is_denied_and_audited(self):
        with self.assertRaises(PermissionError):
            self.service.create(
                project_id="p1",
                owner_user_id="attacker",
                now=NOW,
            )
        self.assertEqual(
            self.repo.audit[-1].event_type,
            ShareAuditEventType.DENIED_OWNER_MISMATCH,
        )

    def test_resolve_is_read_only_capability_and_revocation_is_immediate(self):
        issued = self.service.create(
            project_id="p1",
            owner_user_id="u1",
            now=NOW,
        )
        resolution = self.service.resolve(issued.token, now=NOW)
        self.assertTrue(resolution.granted)
        self.assertEqual(resolution.project_id, "p1")
        self.assertEqual(resolution.scope.value, "PROJECT_READ_ONLY")

        self.service.revoke(
            share_link_id=issued.link.id,
            owner_user_id="u1",
            now=NOW + timedelta(minutes=1),
        )
        denied = self.service.resolve(
            issued.token,
            now=NOW + timedelta(minutes=2),
        )
        self.assertEqual(denied.status, ShareResolutionStatus.REVOKED)

    def test_expired_token_is_denied(self):
        issued = self.service.create(
            project_id="p1",
            owner_user_id="u1",
            now=NOW,
            ttl=timedelta(hours=1),
        )
        resolution = self.service.resolve(
            issued.token,
            now=NOW + timedelta(hours=1),
        )
        self.assertEqual(resolution.status, ShareResolutionStatus.EXPIRED)
        self.assertEqual(
            self.repo.audit[-1].event_type,
            ShareAuditEventType.DENIED_EXPIRED,
        )

    def test_unknown_or_malformed_token_does_not_leak_project_existence(self):
        malformed = self.service.resolve("tiny", now=NOW)
        unknown = self.service.resolve(
            "A" * 43,
            now=NOW,
        )
        self.assertEqual(malformed.status, ShareResolutionStatus.NOT_FOUND)
        self.assertEqual(unknown.status, ShareResolutionStatus.NOT_FOUND)
        self.assertIsNone(malformed.project_id)
        self.assertIsNone(unknown.project_id)

    def test_ttl_is_bounded(self):
        with self.assertRaises(ValueError):
            self.service.create(
                project_id="p1",
                owner_user_id="u1",
                now=NOW,
                ttl=timedelta(days=366),
            )


if __name__ == "__main__":
    unittest.main()
