import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "dzs" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_dzs import DzsAdapter
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


ERASMUS = (ROOT / "connectors" / "dzs" / "fixtures" / "erasmus-2026.html").read_text(encoding="utf-8")
ESC = (ROOT / "connectors" / "dzs" / "fixtures" / "esc-2026.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class DzsAdapterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if request.url.path == "/en/node/3607":
            return httpx.Response(200, text=ERASMUS, headers={"content-type": "text/html"}, request=request)
        if request.url.path.rstrip("/") == "/program/evropsky-sbor-solidarity/projekty-granty":
            return httpx.Response(200, text=ESC, headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = DzsAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="dzs-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_creates_actions_not_event_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        titles = [item.title_hint for item in page.items]
        self.assertTrue(any("Výměna mládeže" in title for title in titles))
        self.assertTrue(any("Vzdělávání dospělých" in title for title in titles))
        self.assertTrue(any("Solidární projekty" in title for title in titles))
        self.assertFalse(any("Webinář" in title for title in titles))

    async def test_upcoming_deadline_is_selected_and_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                youth = next(item for item in page.items if "Výměna mládeže" in item.title_hint)
                esc = next(item for item in page.items if "Solidární projekty" in item.title_hint)
                youth_record = (await adapter.fetch_record(ctx, youth)).record
                esc_record = (await adapter.fetch_record(ctx, esc)).record
                calls_after_discovery = self.calls
            finally:
                await client.aclose()

        self.assertEqual(youth_record.raw_fields["submissionCloseAt"], "2026-10-01T10:00:00+00:00")
        self.assertEqual(esc_record.raw_fields["submissionCloseAt"], "2026-10-01T10:00:00+00:00")
        self.assertEqual(youth_record.raw_fields["fundingInstrumentType"], "GRANT")
        self.assertEqual(esc_record.raw_fields["fundingInstrumentType"], "GRANT")
        self.assertEqual(youth_record.native_status, "OPEN")
        self.assertEqual(calls_after_discovery, 2)

    async def test_past_only_esc_action_is_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                humanitarian = next(item for item in page.items if "humanitární" in item.title_hint)
                record = (await adapter.fetch_record(ctx, humanitarian)).record
            finally:
                await client.aclose()
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["submissionCloseAt"], "2026-04-23T15:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
