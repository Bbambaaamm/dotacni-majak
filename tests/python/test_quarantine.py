import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.quarantine import (
    InMemoryQuarantineRepository,
    QuarantineReason,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


class QuarantineTest(unittest.TestCase):
    def test_item_is_unresolved_until_explicit_resolution(self):
        repo = InMemoryQuarantineRepository()
        item = repo.add(
            source_code="NSA",
            external_id="call-1",
            reason=QuarantineReason.VALIDATION_FAILED,
            details="deadline malformed",
            payload_ref="raw:NSA:abc",
            now=NOW,
        )
        self.assertFalse(item.is_resolved)
        self.assertEqual(repo.unresolved(source_code="NSA"), [item])

        resolved = repo.resolve(
            item.id,
            note="fixed parser and reprocessed",
            now=NOW,
        )
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(repo.unresolved(source_code="NSA"), [])


if __name__ == "__main__":
    unittest.main()
