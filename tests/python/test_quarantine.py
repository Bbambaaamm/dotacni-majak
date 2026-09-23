import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.quarantine import (
    InMemoryQuarantineRepository,
    QuarantineReason,
)


class QuarantineTest(unittest.TestCase):
    def test_quarantine_lifecycle_is_separate_from_canonical_publication(self):
        repo = InMemoryQuarantineRepository()
        item = repo.add(
            source_code="NSA",
            external_id="call-1",
            reason=QuarantineReason.VALIDATION_FAILED,
            details="support rate outside allowed range",
            payload_ref="raw/NSA/aa/bb/hash.bin",
        )

        self.assertFalse(item.is_resolved)
        self.assertEqual(repo.unresolved(source_code="NSA"), [item])

        resolved = repo.resolve(
            item.id,
            note="parser fixed and payload reprocessed",
        )
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(repo.unresolved(source_code="NSA"), [])


if __name__ == "__main__":
    unittest.main()
