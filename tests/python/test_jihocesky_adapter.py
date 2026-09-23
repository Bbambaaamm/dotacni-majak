import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "jihocesky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_jihocesky import JihoceskyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


INDEX = (ROOT / "connectors" / "jihocesky" / "fixtures" / "index.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class JihoceskyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/ku_dotace/vyhlasene":
            return httpx.Response(
                200,
                text=INDEX,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if path.startswith("/files/"):
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if path.endswith(".xlsx")
                else "application/zip"
            )
            return httpx.Response(
                200,
                content=b"fixture",
                headers={"content-type": content_type},
                request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = JihoceskyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="jihocesky-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_splits_grants_from_single_official_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(health.status.value, "HEALTHY")
        self.assertEqual(page.total_hint, 2)
        self.assertTrue(all(item.external_id.startswith("JHC-") for item in page.items))

        dental = next(item for item in page.items if "pohotovostnich" in item.external_id)
        self.assertEqual(dental.native_status_hint, "PLANNED")
        self.assertTrue(dental.metadata["submission_open_at"].startswith("2026-12-31T23:00:00"))
        self.assertTrue(dental.metadata["submission_close_at"].startswith("2027-02-28T22:59:59"))

    async def test_fetch_record_reuses_raw_discovery_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                av = next(item for item in page.items if "audiovizualni" in item.external_id)
                result = await adapter.fetch_record(ctx, av)
                record = result.record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["regionCode"], "CZ031")
        self.assertIn("audiovizuálních", record.raw_fields["supportedActivitiesText"])
        self.assertTrue(record.snapshot_ids)
        self.assertEqual(len(record.artifacts), 2)

    async def test_artifact_is_raw_backed(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                record = (await adapter.fetch_record(ctx, page.items[1])).record
                artifact = await adapter.fetch_artifact(ctx, record.artifacts[0])
            finally:
                await client.aclose()
        self.assertTrue(artifact.snapshot_id)
        self.assertEqual(artifact.state.value, "MODIFIED")


if __name__ == "__main__":
    unittest.main()
