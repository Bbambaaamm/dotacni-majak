import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "dotaceeu" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))

from dotacni_majak_source_sdk import AdapterContext, HealthStatus, FetchState
from dotacni_majak_source_sdk.testing import (
    FixtureHttpClient,
    FixtureSnapshotStore,
    exercise_adapter_contract,
)
from dotacni_majak_dotaceeu import DotaceEuAdapter

FIXTURE_DIR = ROOT / "connectors" / "dotaceeu" / "fixtures"
LISTING_HTML = (FIXTURE_DIR / "listing.html").read_text(encoding="utf-8")
DETAIL_HTML = (FIXTURE_DIR / "call-109.html").read_text(encoding="utf-8")
CALENDAR_XLSX = (FIXTURE_DIR / "calendar.xlsx").read_bytes()

LISTING_URL = "https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy"
CALENDAR_URL = "https://www.dotaceeu.cz/media/calendar/vyzvy.xlsx"
DETAIL_URL_MZP_109 = (
    "https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy/"
    "obdobi-2021-2027/05-operacni-program-zivotni-prostredi-2021-2027/"
    "mzp_109-vyzva,-sc-1-3,-opatreni-1-3-3,-prubezna"
)
DETAIL_URL_IROP_120 = (
    "https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy/"
    "obdobi-2021-2027/06-integrovany-regionalni-operacni-program/"
    "120-vyzva-irop-kyberneticka-bezpecnost-ii"
)

# Canonical expected output for the 109 call golden fixture
# (Výzva 109 výzva, SC 1.3, opatření 1.3.3, průběžná).
EXPECTED = {
    "external_id": "DOTACEEU-mzp-109-vyzva-sc-1-3-opatreni-1-3-3-prubezna",
    "native_status": "OPEN",
    "call_code": "05_26_109",
    "call_type": "Průběžná",
    "programme": "Operační program Životní prostředí 2021—2027",
    "programming_period": "2021-2027",
    "priority_axis": "Životní prostředí",
    "eligible_applicants": "Bez omezení, dle PrŽaP",
    "access_at": "2026-07-01T22:00:00+00:00",
    "submission_open_at": "2026-07-15T22:00:00+00:00",
    "submission_close_at": "2026-12-17T22:59:59.999999+00:00",
    "more_info_url": "https://www.opzp.cz/dotace/109-vyzva/",
    "history_count": 2,
    "history_entries": [
        ("03.07.2026", "Změna stavu: na Vyhlášená"),
        ("17.07.2026", "Změna stavu: na Otevřená"),
    ],
    "discovery_methods": {"XLSX"},
}


def make_fixture_http():
    http = FixtureHttpClient()
    http.add("GET", LISTING_URL, content=LISTING_HTML)
    http.add("GET", CALENDAR_URL, content=CALENDAR_XLSX)
    http.add("GET", DETAIL_URL_MZP_109, content=DETAIL_HTML)
    http.add("GET", DETAIL_URL_IROP_120, content=DETAIL_HTML)
    return http


def make_fixture_context(http, *, now):
    snapshots = FixtureSnapshotStore()
    return AdapterContext(
        run_id="dotaceeu-golden-fixture-contract",
        http=http,
        logger=None,
        budget=None,
        snapshots=snapshots,
        now=now,
    )


class DotaceEuGoldenFixtureContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

    async def test_descriptor_contract_holds(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        await exercise_adapter_contract(adapter, ctx, require_items=True)
        self.assertEqual(adapter.descriptor.code, "DOTACEEU")

    async def test_healthcheck_reports_healthy_on_golden_listing(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        report = await adapter.healthcheck(ctx)
        self.assertEqual(report.status, HealthStatus.HEALTHY)

    async def test_discovery_merges_html_and_xlsx_and_deduplicates(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        page = await adapter.discover(ctx, None)

        self.assertTrue(page.is_complete)
        self.assertEqual(page.total_hint, 2)
        methods = {
            item.metadata.get("discovery_method") for item in page.items
        }
        self.assertEqual(methods, EXPECTED["discovery_methods"])
        self.assertTrue(
            all("calendar_snapshot_id" in item.metadata for item in page.items)
        )
        self.assertTrue(
            all("listing_snapshot_id" in item.metadata for item in page.items)
        )

    async def test_golden_fixture_produces_canonical_expected_record(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        page = await adapter.discover(ctx, None)
        target = next(
            item for item in page.items if "mzp-109" in item.external_id
        )
        result = await adapter.fetch_record(ctx, target, None)

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.external_id, EXPECTED["external_id"])
        self.assertEqual(record.native_status, EXPECTED["native_status"])
        raw = record.raw_fields
        self.assertEqual(raw["callCode"], EXPECTED["call_code"])
        self.assertEqual(raw["callType"], EXPECTED["call_type"])
        self.assertEqual(raw["programme"], EXPECTED["programme"])
        self.assertEqual(
            raw["programmingPeriod"], EXPECTED["programming_period"]
        )
        self.assertEqual(raw["priorityAxis"], EXPECTED["priority_axis"])
        self.assertEqual(
            raw["eligibleApplicantsText"], EXPECTED["eligible_applicants"]
        )
        self.assertEqual(raw["submissionOpenAt"], EXPECTED["submission_open_at"])
        self.assertEqual(
            raw["submissionCloseAt"], EXPECTED["submission_close_at"]
        )
        self.assertEqual(raw["applicationAccessAt"], EXPECTED["access_at"])
        self.assertEqual(raw["moreInfoUrl"], EXPECTED["more_info_url"])
        self.assertTrue(record.snapshot_ids)

    async def test_golden_fixture_history_preserved_canonical(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        page = await adapter.discover(ctx, None)
        target = next(
            item for item in page.items if "mzp-109" in item.external_id
        )
        result = await adapter.fetch_record(ctx, target, None)

        history = result.record.raw_fields["history"]
        self.assertEqual(len(history), EXPECTED["history_count"])
        for entry, (exp_date, exp_change) in zip(
            history, EXPECTED["history_entries"]
        ):
            self.assertEqual(entry["date"], exp_date)
            self.assertEqual(entry["change"], exp_change)

    async def test_golden_fixture_raw_snapshots_cover_listing_xlsx_and_detail(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        page = await adapter.discover(ctx, None)
        target = next(
            item for item in page.items if "mzp-109" in item.external_id
        )
        result = await adapter.fetch_record(ctx, target, None)

        self.assertTrue(result.record.snapshot_ids)
        self.assertGreaterEqual(len(ctx.snapshots.snapshots), 3)

    async def test_golden_fixture_no_invented_unknown_fields(self):
        adapter = DotaceEuAdapter()
        http = make_fixture_http()
        ctx = make_fixture_context(http, now=self.now)
        page = await adapter.discover(ctx, None)
        target = next(
            item for item in page.items if "mzp-109" in item.external_id
        )
        result = await adapter.fetch_record(ctx, target, None)

        raw = result.record.raw_fields
        expected_keys = {
            "callCode", "callType", "programmingPeriod", "programme",
            "priorityAxis", "eligibleApplicantsText", "applicationAccessAt",
            "submissionOpenAt", "submissionCloseAt", "officialStatusText",
            "moreInfoUrl", "history", "discoveryMethod",
        }
        self.assertEqual(set(raw.keys()), expected_keys)
        for key in ("callCode", "callType", "programme", "priorityAxis"):
            self.assertIsNotNone(
                raw[key], f"{key} must not be None for golden fixture"
            )


if __name__ == "__main__":
    unittest.main()