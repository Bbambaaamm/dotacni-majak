import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "jihomoravsky" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_jihomoravsky.adapter import AREAS_URL, JihomoravskyAdapter
from dotacni_majak_source_sdk import AdapterContext


class Response:
    def __init__(self, text, status_code=200, headers=None):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}


class FakeHttp:
    def __init__(self, mapping):
        self.mapping = mapping

    async def get(self, url, headers=None):
        return self.mapping.get(str(url), Response("", 404))


def fixture(name):
    return (ROOT / "connectors" / "jihomoravsky" / "fixtures" / name).read_text(encoding="utf-8")


class JihomoravskyConnectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_walks_areas_to_folders_to_grants_and_dedupes(self):
        folder_a = "https://dotace.kr-jihomoravsky.cz/Folders/761-1-Vzdelavani%2Bsport%2Ba%2Bvolny%2Bcas.aspx"
        folder_b = "https://dotace.kr-jihomoravsky.cz/Folders/757-1-Regionalni%2Brozvoj.aspx"
        http = FakeHttp({
            AREAS_URL: Response(fixture("areas.html")),
            folder_a: Response(fixture("folder.html")),
            folder_b: Response(fixture("folder.html")),
        })
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 7, 1, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            page = await JihomoravskyAdapter().discover(ctx, None)

        self.assertEqual(page.total_hint, 2)
        self.assertEqual({x.external_id for x in page.items}, {"JMK-24209", "JMK-24084"})

    async def test_detail_extracts_dates_finance_applicants_and_artifacts(self):
        url = "https://dotace.kr-jihomoravsky.cz/Grants/24084-506-Rozvoj.aspx"
        item = type("I", (), {
            "external_id": "JMK-24084",
            "detail_url": url,
            "title_hint": "Rozvoj turistické infrastruktury Jihomoravského kraje 2026",
            "metadata": {"discovery_method": "official-area-folder"},
        })()
        http = FakeHttp({url: Response(fixture("detail.html"))})
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 7, 15, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            result = await JihomoravskyAdapter().fetch_record(ctx, item)

        record = result.record
        assert record is not None
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["regionCode"], "CZ064")
        self.assertEqual(record.raw_fields["totalAllocationMinor"], 1_600_000_000)
        self.assertEqual(record.raw_fields["grantAmountMinMinor"], 10_000_000)
        self.assertEqual(record.raw_fields["grantAmountMaxMinor"], 200_000_000)
        self.assertEqual(record.raw_fields["ownContributionMinBps"], 4000)
        self.assertEqual(record.raw_fields["submissionOpenAt"], "2026-06-30T06:00:00+00:00")
        self.assertEqual(record.raw_fields["submissionCloseAt"], "2026-08-10T12:00:00+00:00")
        self.assertEqual(len(record.artifacts), 3)

    async def test_explicit_no_cofinancing_maps_to_zero_bps(self):
        url = "https://dotace.kr-jihomoravsky.cz/Grants/23791-506-Pecujici.aspx"
        item = type("I", (), {
            "external_id": "JMK-23791",
            "detail_url": url,
            "title_hint": "Pečující",
            "metadata": {},
        })()
        http = FakeHttp({url: Response(fixture("zero-cofinancing.html"))})
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 2, 10, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            result = await JihomoravskyAdapter().fetch_record(ctx, item)

        record = result.record
        assert record is not None
        self.assertEqual(record.raw_fields["ownContributionMinBps"], 0)


if __name__ == "__main__":
    unittest.main()
