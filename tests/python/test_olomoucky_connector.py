import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "olomoucky" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_olomoucky.adapter import CLOSED_URL, CURRENT_URL, OlomouckyAdapter
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
    return (ROOT / "connectors" / "olomoucky" / "fixtures" / name).read_text(encoding="utf-8")


class OlomouckyConnectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_combines_current_and_closed_indexes(self):
        http = FakeHttp({
            CURRENT_URL: Response(fixture("current.html")),
            CLOSED_URL: Response(fixture("closed.html")),
        })
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            page = await OlomouckyAdapter().discover(ctx, None)

        self.assertEqual(page.total_hint, 3)
        self.assertIn("OLK-2026-06_07", {x.external_id for x in page.items})

    async def test_closed_index_is_explicit_status_and_detail_is_parsed(self):
        url = "https://www.olkraj.cz/dotace-granty-prispevky-krajske-dotacni-programy-2026/06-07-program-na-podporu-vystavby-a-rekonstrukci-sportovnich-zarizeni-v-obcich-olomouckeho-kraje-v-roce-2026-prijem-zadosti-7-4-17-4-2026"
        http = FakeHttp({url: Response(fixture("detail.html"))})
        item = type("I", (), {
            "external_id": "OLK-2026-06_07",
            "detail_url": url,
            "title_hint": "06_07 sport",
            "metadata": {
                "closed_index": True,
                "discovery_method": "official-current-or-closed-index",
            },
        })()

        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 3, 1, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            result = await OlomouckyAdapter().fetch_record(ctx, item)

        record = result.record
        assert record is not None
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["sourceCallCode"], "06_07")
        self.assertEqual(record.raw_fields["regionCode"], "CZ071")
        self.assertEqual(record.raw_fields["submissionCloseAt"], "2026-04-17T10:00:00+00:00")
        self.assertEqual(record.raw_fields["applicationUrl"], "https://www.olkraj.cz/portal/")
        self.assertTrue(any(a.role == "CALL_DOCUMENT" for a in record.artifacts))
        self.assertTrue(any(a.role == "APPLICATION_FORM" for a in record.artifacts))

    async def test_short_start_date_infers_year_from_closing_date(self):
        url = "https://www.olkraj.cz/dotace-granty-prispevky-krajske-dotacni-programy-2026/06-07-x"
        http = FakeHttp({url: Response(fixture("detail.html"))})
        item = type("I", (), {
            "external_id": "OLK-2026-06_07",
            "detail_url": url,
            "title_hint": "06_07",
            "metadata": {"closed_index": False},
        })()
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            result = await OlomouckyAdapter().fetch_record(ctx, item)
        record = result.record
        assert record is not None
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["submissionOpenAt"], "2026-04-06T22:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
