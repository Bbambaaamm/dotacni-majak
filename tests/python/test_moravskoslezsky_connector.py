import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "moravskoslezsky" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_moravskoslezsky.adapter import (
    MoravskoslezskyAdapter,
    ROOT_URL,
)
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
        self.calls = []

    async def get(self, url, headers=None):
        self.calls.append(str(url))
        value = self.mapping.get(str(url))
        if value is None:
            return Response("", status_code=404)
        return value


def fixture(name):
    return (ROOT / "connectors" / "moravskoslezsky" / "fixtures" / name).read_text(encoding="utf-8")


class MoravskoslezskyConnectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_discover_finds_only_official_detail_urls_and_pagination(self):
        page2 = "<html><body><a href='/cs/temata/dotace/podpora-vedy-a-vyzkumu-v-moravskoslezskem-kraji-2026-25726/'>Věda 2026</a></body></html>"
        http = FakeHttp({
            ROOT_URL: Response(fixture("index.html")),
            ROOT_URL + "?page=2": Response(page2),
        })
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r1",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 3, 20, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            page = await MoravskoslezskyAdapter().discover(ctx, None)

        self.assertTrue(page.is_complete)
        self.assertEqual(page.total_hint, 3)
        self.assertEqual(
            {item.external_id for item in page.items},
            {"MSK-25606", "MSK-24920", "MSK-25726"},
        )

    async def test_fetch_record_extracts_deadline_code_region_and_artifacts(self):
        url = "https://www.msk.cz/cs/temata/dotace/dotacni-program-na-podporu-sboru-dobrovolnych-hasicu-v-roce-2026-25606/"
        http = FakeHttp({url: Response(fixture("detail.html"))})
        adapter = MoravskoslezskyAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r1",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 4, 2, 10, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            discovery = (await adapter.discover(
                AdapterContext(
                    run_id="r0",
                    http=FakeHttp({ROOT_URL: Response("<a href='" + url + "'>Hasiči</a>")}),
                    logger=None,
                    budget=None,
                    now=ctx.now,
                    snapshots=ctx.snapshots,
                ),
                None,
            )).items[0]
            result = await adapter.fetch_record(ctx, discovery)

        record = result.record
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.external_id, "MSK-25606")
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["sourceCallCode"], "KH/01/2026")
        self.assertEqual(record.raw_fields["regionCode"], "CZ080")
        self.assertIsNotNone(record.raw_fields["submissionOpenAt"])
        self.assertIsNotNone(record.raw_fields["submissionCloseAt"])
        self.assertGreaterEqual(len(record.artifacts), 2)
        self.assertTrue(record.snapshot_ids)

    async def test_multiple_application_rounds_are_not_merged_into_fake_range(self):
        url = "https://www.msk.cz/cs/temata/dotace/bezplatne-stravovani-26141/"
        http = FakeHttp({url: Response(fixture("detail-multiple-rounds.html"))})
        adapter = MoravskoslezskyAdapter()
        item = type("I", (), {
            "external_id": "MSK-26141",
            "detail_url": url,
            "title_hint": "Bezplatné stravování",
            "metadata": {},
        })()
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r1",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 6, 1, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            result = await adapter.fetch_record(ctx, item)

        record = result.record
        assert record is not None
        self.assertEqual(record.native_status, "UNKNOWN")
        self.assertIsNone(record.raw_fields["submissionOpenAt"])
        self.assertIsNone(record.raw_fields["submissionCloseAt"])
        self.assertIn("prvním kole", record.raw_fields["deadlineText"])


if __name__ == "__main__":
    unittest.main()
