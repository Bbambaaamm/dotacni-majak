import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.local_publish import render_import_sql
from dotacni_majak_ingestion.normalization import (
    DotaceEuGrantNormalizer,
    EuFundingGrantNormalizer,
    NsaGrantNormalizer,
)
from dotacni_majak_source_sdk import DiscoveryItem, NativeRecord


CAPTURED = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


class ConnectorNormalizationTest(unittest.TestCase):
    def test_nsa_mapping_is_source_aware(self):
        item = DiscoveryItem(
            external_id="16/2026",
            detail_url="https://nsa.gov.cz/dotace/test",
            title_hint="Regiony 2026",
            metadata={"listing_url": "https://nsa.gov.cz/dotace-investicni/"},
        )
        record = NativeRecord(
            source_code="NSA",
            external_id="16/2026",
            detail_url=item.detail_url,
            native_title="Regiony 2026",
            native_status="OPEN",
            raw_fields={
                "descriptionText": "Technické zhodnocení sportovních zařízení.",
                "callType": "investiční",
                "submissionCloseAt": "2026-12-31T23:00:00+00:00",
            },
            snapshot_ids=["NSA:" + "a" * 64],
        )
        grant = NsaGrantNormalizer().normalize(item, record, CAPTURED)
        self.assertEqual(grant.currency_code, "CZK")
        self.assertEqual(grant.retrieval_mode, "HTML")
        self.assertEqual(grant.status, "OPEN")
        self.assertIn("sportovních zařízení", grant.supported_activities)

    def test_dotaceeu_unknown_status_stays_draft(self):
        item = DiscoveryItem(
            external_id="DOTACEEU-test",
            detail_url="https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy/obdobi-x/test",
        )
        record = NativeRecord(
            source_code="DOTACEEU",
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title="Test",
            native_status="UNKNOWN",
            raw_fields={"programme": "IROP", "eligibleApplicantsText": "Obce"},
            snapshot_ids=["DOTACEEU:" + "b" * 64],
        )
        grant = DotaceEuGrantNormalizer().normalize(item, record, CAPTURED)
        self.assertEqual(grant.status, "DRAFT")
        self.assertIn("Obce", grant.summary)

    def test_eu_funding_maps_api_eur_and_status_code(self):
        item = DiscoveryItem(
            external_id="ISF-2026-TEST",
            detail_url="https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/ISF-2026-TEST",
            metadata={"deadline": "2026-11-30T00:00:00+00:00"},
        )
        record = NativeRecord(
            source_code="EU_FT",
            external_id=item.external_id,
            detail_url=item.detail_url,
            native_title="EU infrastructure call",
            native_status="31094502",
            raw_fields={
                "summary": "Support for infrastructure.",
                "reference": "ref-1",
                "metadata": {
                    "frameworkProgramme": ["43252368"],
                    "startDate": ["2026-09-01T00:00:00+00:00"],
                    "deadlineDate": ["2026-11-30T00:00:00+00:00"],
                    "callTitle": ["EU infrastructure"],
                    "type": ["1"],
                    "topicConditions": ["<p>Eligible infrastructure activities.</p>"],
                },
            },
            snapshot_ids=["EU_FT:" + "c" * 64],
        )
        grant = EuFundingGrantNormalizer().normalize(item, record, CAPTURED)
        self.assertEqual(grant.status, "OPEN")
        self.assertEqual(grant.currency_code, "EUR")
        self.assertEqual(grant.retrieval_mode, "API")
        self.assertIn("Eligible infrastructure activities", grant.supported_activities)

        sql = render_import_sql(
            [grant],
            source_id=grant.source_id,
            source_code=grant.source_code,
            source_name=grant.source_name,
            adapter_version="0.1.0",
            captured_at=CAPTURED.isoformat(),
        )
        self.assertIn("'API'", sql)
        self.assertIn("'EUR'", sql)


if __name__ == "__main__":
    unittest.main()
