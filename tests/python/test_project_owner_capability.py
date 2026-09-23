import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "project-access" / "src"))

from dotacni_majak_project_access import (
    InMemoryProjectAccessRepository,
    OwnerAuditEventType,
    ProjectOwnerCapabilityService,
)


NOW = datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc)


class ProjectOwnerCapabilityTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryProjectAccessRepository()
        self.service = ProjectOwnerCapabilityService(self.repo)

    def test_raw_token_is_returned_once_but_only_hash_is_persisted(self):
        issued = self.service.issue("p1", now=NOW)
        self.assertGreaterEqual(len(issued.token), 40)
        self.assertNotEqual(issued.capability.token_hash, issued.token)
        self.assertNotIn(issued.token, repr(issued.capability))
        self.assertTrue(self.service.verify("p1", issued.token, now=NOW))

    def test_owner_token_is_project_scoped_against_idor(self):
        issued = self.service.issue("p1", now=NOW)
        self.assertFalse(self.service.verify("p2", issued.token, now=NOW))
        self.assertEqual(
            self.repo.audit[-1].event_type,
            OwnerAuditEventType.DENIED_PROJECT_MISMATCH,
        )

    def test_rotation_invalidates_old_token(self):
        issued = self.service.issue("p1", now=NOW)
        rotated = self.service.rotate("p1", issued.token, now=NOW)
        self.assertEqual(rotated.capability.generation, 2)
        self.assertFalse(self.service.verify("p1", issued.token, now=NOW))
        self.assertTrue(self.service.verify("p1", rotated.token, now=NOW))

    def test_revocation_is_immediate(self):
        issued = self.service.issue("p1", now=NOW)
        self.service.revoke("p1", issued.token, now=NOW)
        self.assertFalse(self.service.verify("p1", issued.token, now=NOW))
        self.assertEqual(
            self.repo.audit[-1].event_type,
            OwnerAuditEventType.DENIED_REVOKED,
        )

    def test_short_or_unknown_token_is_denied_without_project_leak(self):
        self.assertFalse(self.service.verify("p1", "tiny", now=NOW))
        self.assertFalse(self.service.verify("p1", "A" * 43, now=NOW))
        self.assertIsNone(self.repo.audit[-1].project_id)


if __name__ == "__main__":
    unittest.main()
