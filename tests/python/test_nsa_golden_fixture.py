import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "nsa" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "search" / "src"))

from dotacni_majak_source_sdk.testing import (
    FixtureHttpClient,
    FixtureSnapshotStore,
    exercise_adapter_contract,
)
from dotacni_majak_source_sdk import AdapterContext, HealthStatus, FetchState
from dotacni_majak_nsa import NsaAdapter
from dotacni_majak_search.ontology import OntologyIndex

FIXTURE_DIR = ROOT / "connectors" / "nsa" / "fixtures"
LISTING_HTML = (FIXTURE_DIR / "investment-listing.html").read_text(encoding="utf-8")
DETAIL_HTML = (FIXTURE_DIR / "call-16-2026.html").read_text(encoding="utf-8")
ONTOLOGY = OntologyIndex.from_directory(ROOT / "data" / "ontology" / "v1")

LISTING_URL = "https://nsa.gov.cz/dotace-investicni/"
PARASPORT_URL = "https://nsa.gov.cz/dotace-neinvesticni-parasport/"
DETAIL_URL = "https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/"

# Canonical expected output for the NSA golden fixture (Výzva 16/2026,
# Regiony 2026 - investice pod 10 mil. Kč). These are derived from the
# public NSA detail page and frozen here as the regression contract.
EXPECTED = {
    "external_id": "16/2026",
    "native_status": "CLOSED",
    "allocation_czk": 505_000_000,
    "call_type": "průběžnou nesoutěžní",
    "description_contains": "technické zhodnocení sportovních zařízení",
    "submission_open_at": "2025-12-18T11:00:00+00:00",
    "submission_close_at": "2026-01-19T11:00:00+00:00",
    "announced_at": "2025-11-13T23:00:00+00:00",
    "artifact_roles": {
        "Aktuální znění Výzvy": "CALL_DOCUMENT",
        "Návod na vyplnění žádosti a další upozornění k Výzvě": "GUIDELINES",
        "Nejčastější otázky a odpovědi": "FAQ",
        "3. Formulář investičního záměru": "ANNEX",
    },
    "call_document_required": True,
    "snapshot_count_min": 1,
}


def make_fixture_http():
    http = FixtureHttpClient()
    http.add("GET", LISTING_URL, content=LISTING_HTML)
    http.add("GET", "https://nsa.gov.cz/dotace-neinvesticni/", content=LISTING_HTML)
    http.add("GET", PARASPORT_URL, content=LISTING_HTML)
    http.add("GET", DETAIL_URL, content=DETAIL_HTML)
    return http


def make_fixture_context(http, *, now):
    snapshots = FixtureSnapshotStore()
    return AdapterContext(
        run_id="nsa-golden-fixture-contract",
        http=http,
        logger=None,
        budget=None,
        snapshots=snapshots,
        now=now,
    )


class NsaGoldenFixtureContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)

    async def test_descriptor_contract_holds(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            await exercise_adapter_contract(adapter, ctx, require_items=True)
        finally:
            pass  # FixtureHttpClient has no async cleanup
        self.assertEqual(adapter.descriptor.code, "NSA")

    async def test_healthcheck_reports_healthy_on_golden_listing(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            health = await adapter.healthcheck(ctx)
        finally:
            pass  # FixtureHttpClient has no async cleanup
        self.assertEqual(health.status, HealthStatus.HEALTHY)

    async def test_discovery_yields_16_2026_and_17_2026_from_golden_listing(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            page = await adapter.discover(ctx, None)
        finally:
            pass  # FixtureHttpClient has no async cleanup
        self.assertTrue(page.is_complete)
        external_ids = [item.external_id for item in page.items]
        self.assertIn("16/2026", external_ids)
        self.assertIn("17/2026", external_ids)
        self.assertEqual(len(external_ids), 2)
        self.assertTrue(
            all("listing_snapshot_id" in item.metadata for item in page.items)
        )

    async def test_golden_fixture_produces_canonical_expected_record(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            await exercise_adapter_contract(adapter, ctx, require_items=True)
            page = await adapter.discover(ctx, None)
            result = await adapter.fetch_record(ctx, page.items[0], None)
        finally:
            pass  # FixtureHttpClient has no async cleanup

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.external_id, EXPECTED["external_id"])
        self.assertEqual(record.native_status, EXPECTED["native_status"])
        self.assertEqual(
            record.raw_fields["allocationCzk"], EXPECTED["allocation_czk"]
        )
        self.assertEqual(
            record.raw_fields["callType"], EXPECTED["call_type"]
        )
        self.assertIn(
            EXPECTED["description_contains"], record.raw_fields["descriptionText"]
        )
        # Deadline / funding evidence preserved in canonical fields.
        self.assertEqual(
            record.raw_fields["submissionOpenAt"], EXPECTED["submission_open_at"]
        )
        self.assertEqual(
            record.raw_fields["submissionCloseAt"], EXPECTED["submission_close_at"]
        )
        self.assertEqual(
            record.raw_fields["announcedAt"], EXPECTED["announced_at"]
        )
        # Artifact roles match canonical expectation.
        roles = {artifact.title: artifact.role for artifact in record.artifacts}
        for title, role in EXPECTED["artifact_roles"].items():
            self.assertIn(title, roles, f"missing artifact {title!r}")
            self.assertEqual(roles[title], role)
        call_document = next(
            a for a in record.artifacts if a.role == "CALL_DOCUMENT"
        )
        self.assertTrue(call_document.required)
        # RAW-first: at least one snapshot per the adapter contract.
        self.assertGreaterEqual(len(record.snapshot_ids), EXPECTED["snapshot_count_min"])

    async def test_golden_fixture_description_maps_to_sport_infrastructure_terms(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            await exercise_adapter_contract(adapter, ctx, require_items=True)
            page = await adapter.discover(ctx, None)
            result = await adapter.fetch_record(ctx, page.items[0], None)
        finally:
            pass  # FixtureHttpClient has no async cleanup

        resolved = ONTOLOGY.resolve(result.record.raw_fields["descriptionText"])
        # The description "výstavbu a technické zhodnocení sportovních zařízení
        # místního významu … bezbariérových přístupů" ontology-resolves to
        # generic sport-infrastructure terms. Those terms are the bridge between
        # this golden fixture and a future "rekonstrukce tenisových kurtů" query:
        # TENNIS_COURT → OUTDOOR_SPORT_FACILITY → SPORT_FACILITY →
        # SPORT_INFRASTRUCTURE (verified in test_ontology_v1).
        self.assertIn("SPORT_INFRASTRUCTURE", resolved)
        self.assertIn("SPORT_FACILITY", resolved)
        self.assertIn("TECHNICAL_IMPROVEMENT", resolved)
        self.assertIn("INVESTMENT", resolved)
        self.assertIn("SPORT", resolved)
        # Explicit construction / accessibility / reconstruction cues are NOT in
        # this description text — they would appear in a tennis-specific fixture
        # and should be covered by a separate golden fixture when available.

    async def test_golden_fixture_snapshot_ids_are_non_empty(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            await exercise_adapter_contract(adapter, ctx, require_items=True)
            page = await adapter.discover(ctx, None)
            result = await adapter.fetch_record(ctx, page.items[0], None)
        finally:
            pass  # FixtureHttpClient has no async cleanup
        self.assertTrue(result.record.snapshot_ids)
        self.assertGreaterEqual(len(result.record.snapshot_ids), 1)

    async def test_golden_fixture_raw_snapshot_store_receives_listing_and_detail(self):
        adapter = NsaAdapter()
        http = make_fixture_http()
        try:
            ctx = make_fixture_context(http, now=self.now)
            await exercise_adapter_contract(adapter, ctx, require_items=True)
        finally:
            pass  # FixtureHttpClient has no async cleanup
        self.assertGreaterEqual(len(ctx.snapshots.snapshots), 1)


if __name__ == "__main__":
    unittest.main()
