import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "tacr" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient
from dotacni_majak_tacr import TacrAdapter


HOME = (ROOT / "connectors" / "tacr" / "fixtures" / "home.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "tacr" / "fixtures" / "sigma-18.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class TacrAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "":
            return httpx.Response(200, text=HOME, headers={"content-type": "text/html"}, request=request)
        if "osmnacta-verejna-soutez" in path:
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"}, request=request)
        if "call-2026-6" in path:
            return httpx.Response(200, text=DETAIL.replace("730 000 Kč", "150 000 €"), headers={"content-type": "text/html"}, request=request)
        if path.startswith("/wp-content/uploads/"):
            return httpx.Response(200, content=b"fixture", headers={"content-type": "application/pdf"}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = TacrAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="tacr-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_only_uses_current_support_competitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()
        self.assertEqual(page.total_hint, 2)
        self.assertTrue(all("/soutez/" in str(item.detail_url) for item in page.items))
        self.assertTrue(all(item.native_status_hint == "OPEN" for item in page.items))

    async def test_sigma_detail_extracts_exact_deadline_and_finance(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if "sigma" in str(i.detail_url))
                record = (await adapter.fetch_record(ctx, item)).record
                call_doc = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                artifact = await adapter.fetch_artifact(ctx, call_doc)
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["submissionOpenAt"], "2026-09-10T07:00:00+00:00")
        self.assertEqual(record.raw_fields["submissionCloseAt"], "2026-10-27T15:29:59+00:00")
        self.assertEqual(record.raw_fields["allocationAmountMinor"], 1000000000)
        self.assertEqual(record.raw_fields["allocationCurrency"], "CZK")
        self.assertEqual(record.raw_fields["maxSupportAmountMinor"], 73000000)
        self.assertEqual(record.raw_fields["maxSupportIntensityBps"], 7000)
        self.assertEqual(record.raw_fields["eligibleApplicantsText"], "Malý podnik")
        self.assertIn("komercializace", record.raw_fields["supportedActivitiesText"])
        self.assertTrue(record.snapshot_ids)
        self.assertTrue(artifact.snapshot_id)

    async def test_artifact_roles_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if "sigma" in str(i.detail_url))
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()
        roles = {a.title: a.role for a in record.artifacts}
        self.assertEqual(roles["Zadávací dokumentace"], "CALL_DOCUMENT")
        self.assertEqual(roles["Všeobecné podmínky v8"], "GUIDELINES")
        self.assertEqual(roles["Příloha č. 1 – Hodnoticí proces"], "ANNEX")


if __name__ == "__main__":
    unittest.main()
