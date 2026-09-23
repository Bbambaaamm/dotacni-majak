import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "zlinsky" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext
from dotacni_majak_zlinsky.adapter import ROOT_URL, ZlinskyAdapter


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
    return (ROOT / "connectors" / "zlinsky" / "fixtures" / name).read_text(encoding="utf-8")


class ZlinskyConnectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_pagination(self):
        page2 = "<a href='/dotace/rp01-26-podpora-vodohospodarske-infrastruktury'>RP01-26 Podpora vodohospodářské infrastruktury</a>"
        http = FakeHttp({
            ROOT_URL: Response(fixture("index.html")),
            ROOT_URL + "?page=2": Response(page2),
        })
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 3, 20, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            page = await ZlinskyAdapter().discover(ctx, None)

        self.assertEqual(page.total_hint, 3)
        self.assertEqual(
            {x.external_id for x in page.items},
            {"ZLK-NFV01-26", "ZLK-RP33-26", "ZLK-RP01-26"},
        )

    async def test_detail_extracts_allocation_dates_area_and_documents(self):
        url = "https://zlinskykraj.cz/dotace/rp33-26-podpora-dostupneho-bydleni"
        http = FakeHttp({url: Response(fixture("detail.html"))})
        adapter = ZlinskyAdapter()
        item = type("I", (), {
            "external_id": "ZLK-RP33-26",
            "detail_url": url,
            "title_hint": "RP33-26 Podpora dostupného bydlení",
            "metadata": {"discovery_method": "official-dotace-index"},
        })()
        with tempfile.TemporaryDirectory() as tmp:
            ctx = AdapterContext(
                run_id="r",
                http=http,
                logger=None,
                budget=None,
                now=datetime(2026, 4, 1, tzinfo=timezone.utc),
                snapshots=LocalRawSnapshotStore(tmp),
            )
            result = await adapter.fetch_record(ctx, item)

        record = result.record
        assert record is not None
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["sourceCallCode"], "RP33-26")
        self.assertEqual(record.raw_fields["totalAllocationMinor"], 3_000_000_000)
        self.assertEqual(record.raw_fields["regionCode"], "CZ072")
        self.assertEqual(record.raw_fields["grantAreaText"], "Rozvojové programy a krizové řízení")
        self.assertIsNotNone(record.raw_fields["applicationUrl"])
        self.assertEqual(len(record.artifacts), 2)
        self.assertTrue(any(a.role == "CALL_DOCUMENT" for a in record.artifacts))
        self.assertTrue(any(a.role == "APPLICATION_FORM" for a in record.artifacts))


if __name__ == "__main__":
    unittest.main()
