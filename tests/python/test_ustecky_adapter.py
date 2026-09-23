import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "ustecky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient
from dotacni_majak_ustecky import UsteckyAdapter


INDEX = (ROOT / "connectors" / "ustecky" / "fixtures" / "index.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "ustecky" / "fixtures" / "detail.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class UsteckyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/dotace":
            return httpx.Response(
                200,
                text="<html><body><h1>Dotace</h1><a>Dotační kalendář</a></body></html>",
                headers={"content-type": "text/html"},
                request=request,
            )
        if path.startswith("/programove-dotace-usteckeho-kraje") or path == "/oblast-informatiky-a-organizacnich-veci":
            return httpx.Response(
                200,
                text=INDEX,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if path in {
            "/podpora-rozvoje-lokalit-pamatek-unesco-v-usteckem-kraji",
            "/program-obnovy-venkova-usteckeho-kraje-2026",
        }:
            return httpx.Response(
                200,
                text=DETAIL,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if path.startswith("/files/"):
            return httpx.Response(
                200,
                content=b"%PDF-fixture",
                headers={"content-type": "application/pdf"},
                request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = UsteckyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="ustecky-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_health_and_discovery_deduplicate_across_area_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(health.status.value, "HEALTHY")
        self.assertEqual(page.total_hint, 2)
        self.assertTrue(all(item.external_id.startswith("ULK-") for item in page.items))

    async def test_detail_extracts_structured_provider_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(
                    item
                    for item in page.items
                    if "unesco" in str(item.detail_url)
                )
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["sourceCallCode"], "111040001")
        self.assertEqual(record.raw_fields["totalAllocationMinor"], 1500000000)
        self.assertEqual(record.raw_fields["regionCode"], "CZ042")
        self.assertIn("obce", record.raw_fields["eligibleApplicantsText"].lower())
        self.assertTrue(record.raw_fields["submissionOpenAt"].startswith("2026-05-20T22:00:00"))
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-06-30T21:59:59"))
        self.assertEqual(len(record.artifacts), 2)
        self.assertTrue(record.snapshot_ids)

    async def test_artifact_is_raw_backed(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                record = (await adapter.fetch_record(ctx, page.items[0])).record
                artifact = await adapter.fetch_artifact(ctx, record.artifacts[0])
            finally:
                await client.aclose()

        self.assertEqual(artifact.state.value, "MODIFIED")
        self.assertTrue(artifact.snapshot_id)


if __name__ == "__main__":
    unittest.main()
