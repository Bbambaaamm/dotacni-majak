import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "karlovarsky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_karlovarsky import KarlovarskyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


INDEX = (ROOT / "connectors" / "karlovarsky" / "fixtures" / "index.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "karlovarsky" / "fixtures" / "detail.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class KarlovarskyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/dotace/dotacni-programy-karlovarskeho-kraje":
            return httpx.Response(200, text=INDEX, headers={"content-type":"text/html"}, request=request)
        if path.startswith("/dotace/program-obedy-do-skol") or path.startswith("/dotace/podpora-kastrace"):
            return httpx.Response(200, text=DETAIL, headers={"content-type":"text/html"}, request=request)
        if path.startswith("/files/"):
            return httpx.Response(200, content=b"%PDF-fixture", headers={"content-type":"application/pdf"}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = KarlovarskyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="kvk-test", http=client, logger=None, budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_finds_program_detail_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()
        self.assertEqual(page.total_hint, 2)
        self.assertTrue(all(x.external_id.startswith("KVK-") for x in page.items))

    async def test_detail_maps_explicit_provider_status_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                record = (await adapter.fetch_record(ctx, page.items[0])).record
            finally:
                await client.aclose()
        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "PLANNED")
        self.assertEqual(record.raw_fields["regionCode"], "CZ041")
        self.assertTrue(record.raw_fields["submissionOpenAt"].startswith("2026-10-17T07:00:00"))
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2027-06-30T14:00:00"))
        self.assertEqual(len(record.artifacts), 2)
        self.assertTrue(record.snapshot_ids)


if __name__ == "__main__":
    unittest.main()
