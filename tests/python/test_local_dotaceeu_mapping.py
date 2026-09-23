import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dotacni_majak_source_sdk import NativeRecord

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from local_ingest_dotaceeu import canonical_status, programme_identity, to_searchable


class DotaceEuLocalMappingTest(unittest.TestCase):
    def record(self, **overrides):
        raw = {
            "callCode": "99",
            "callType": "kolová",
            "programmingPeriod": "2021–2027",
            "programme": "Integrovaný regionální operační program",
            "priorityAxis": "Rozvoj infrastruktury",
            "eligibleApplicantsText": "Obce a jejich organizace",
            "submissionOpenAt": "2026-10-01T00:00:00+00:00",
            "submissionCloseAt": "2026-12-31T22:59:59+00:00",
        }
        raw.update(overrides.pop("raw_fields", {}))
        return NativeRecord(
            source_code="DOTACEEU",
            external_id="DOTACEEU-test-call",
            detail_url="https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy/obdobi-2021-2027/test",
            native_title="Testovací infrastruktura",
            native_status=overrides.pop("native_status", "OPEN"),
            raw_fields=raw,
            snapshot_ids=["DOTACEEU:" + "a" * 64],
            **overrides,
        )

    def test_unknown_status_is_not_made_active(self):
        self.assertEqual(canonical_status("UNKNOWN"), "DRAFT")

    def test_known_cancelled_status_is_preserved(self):
        self.assertEqual(canonical_status("CANCELLED"), "CANCELLED")

    def test_programme_identity_is_stable(self):
        first = programme_identity(self.record())
        second = programme_identity(self.record())
        self.assertEqual(first, second)
        self.assertIn("Integrovaný regionální", first[1])

    def test_mapping_uses_only_official_detail_fields(self):
        mapped = to_searchable(
            self.record(),
            datetime(2026, 9, 24, tzinfo=timezone.utc),
        )
        self.assertEqual(mapped.status, "OPEN")
        self.assertEqual(mapped.provider_name, "DotaceEU.cz")
        self.assertIn("Obce a jejich organizace", mapped.summary)
        self.assertIn("Rozvoj infrastruktury", mapped.supported_activities)
        self.assertEqual(mapped.content_hash, "a" * 64)
        self.assertEqual(mapped.submission_close_at, "2026-12-31T22:59:59+00:00")


if __name__ == "__main__":
    unittest.main()
