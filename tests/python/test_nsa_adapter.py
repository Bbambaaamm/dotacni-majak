import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "nsa" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_nsa import NsaAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


LISTING = (ROOT / "connectors" / "nsa" / "fixtures" / "investment-listing.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "nsa" / "fixtures" / "call-16-2026.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class NsaAdapterTest(unittest.IsolatedAsyncioTestCase):
    def make_handler(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path in {"/dotace-investicni/", "/dotace-neinvesticni/", "/dotace-neinvesticni-parasport/"}:
                return httpx.Response(200, text=LISTING, headers={"content-type": "text/html; charset=UTF-8"}, request=request)
            if path.startswith("/dotace/vyzva-16-2026"):
                return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html; charset=UTF-8"}, request=request)
            if path.startswith("/wp-content/uploads/"):
                return httpx.Response(200, content=b"%PDF-1.7 fixture", headers={"content-type": "application/pdf"}, request=request)
            return httpx.Response(404, request=request)
        return handler

    async def make_context(self, tmp):
        client = GuardedHttpClient(
            allowed_hosts={"nsa.gov.cz", "www.nsa.gov.cz"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.make_handler()),
        )
        ctx = AdapterContext(
            run_id="test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
        )
        return client, ctx

    async def test_discovery_deduplicates_same_calls_across_listings(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.make_context(tmp)
            try:
                page = await NsaAdapter().discover(ctx, None)
            finally:
                await client.aclose()
        self.assertTrue(page.is_complete)
        self.assertEqual(page.total_hint, 2)
        self.assertEqual([x.external_id for x in page.items], ["16/2026", "17/2026"])
        self.assertTrue(all("listing_snapshot_id" in x.metadata for x in page.items))

    async def test_detail_parses_dates_status_allocation_description_and_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.make_context(tmp)
            try:
                adapter = NsaAdapter()
                item = (await adapter.discover(ctx, None)).items[0]
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.external_id, "16/2026")
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["allocationCzk"], 505_000_000)
        self.assertEqual(record.raw_fields["callType"], "průběžnou nesoutěžní")
        self.assertIn("technické zhodnocení sportovních zařízení", record.raw_fields["descriptionText"])
        self.assertTrue(record.snapshot_ids)

        roles = {artifact.title: artifact.role for artifact in record.artifacts}
        self.assertEqual(roles["Aktuální znění Výzvy"], "CALL_DOCUMENT")
        self.assertEqual(roles["Návod na vyplnění žádosti a další upozornění k Výzvě"], "GUIDELINES")
        self.assertEqual(roles["Nejčastější otázky a odpovědi"], "FAQ")
        self.assertEqual(roles["3. Formulář investičního záměru"], "ANNEX")

    async def test_call_document_is_required_and_artifact_is_snapshotted(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.make_context(tmp)
            try:
                adapter = NsaAdapter()
                item = (await adapter.discover(ctx, None)).items[0]
                record = (await adapter.fetch_record(ctx, item)).record
                call_document = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                self.assertTrue(call_document.required)
                result = await adapter.fetch_artifact(ctx, call_document)
            finally:
                await client.aclose()

        self.assertEqual(result.state.value, "MODIFIED")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertTrue(result.snapshot_id)


if __name__ == "__main__":
    unittest.main()
