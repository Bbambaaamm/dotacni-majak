import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "liberecky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_liberecky import LibereckyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


ROOT_HTML = (ROOT / "connectors" / "liberecky" / "fixtures" / "root.html").read_text(encoding="utf-8")
CATEGORY = (ROOT / "connectors" / "liberecky" / "fixtures" / "category.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "liberecky" / "fixtures" / "detail.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class LibereckyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "":
            return httpx.Response(200, text=ROOT_HTML, headers={"content-type":"text/html"}, request=request)
        if path in {"/skolstvi-a-mladez", "/socialni-sluzby"}:
            return httpx.Response(200, text=CATEGORY, headers={"content-type":"text/html"}, request=request)
        if re_detail(path):
            return httpx.Response(200, text=DETAIL, headers={"content-type":"text/html; charset=utf-8"}, request=request)
        if path.startswith("/getFile"):
            return httpx.Response(200, content=b"%PDF-fixture", headers={"content-type":"application/pdf"}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = LibereckyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="liberecky-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_root_category_discovery_uses_stable_numeric_detail_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(health.status.value, "HEALTHY")
        self.assertEqual(page.total_hint, 2)
        self.assertEqual(
            {item.external_id for item in page.items},
            {"LBK-458376", "LBK-458111"},
        )
        self.assertTrue(all(item.metadata["category"] == "Školství a mládež" for item in page.items))

    async def test_detail_extracts_window_allocation_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(item for item in page.items if item.external_id == "LBK-458376")
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["regionCode"], "CZ051")
        self.assertEqual(record.raw_fields["totalAllocationMinor"], 60000000)
        self.assertTrue(record.raw_fields["submissionOpenAt"].startswith("2026-02-24T23:00:00"))
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-11-30T22:59:59"))
        self.assertIn("mimoliberecké", record.raw_fields["summaryText"])
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


def re_detail(path: str) -> bool:
    return path.endswith(".htm") and "-d" in path


if __name__ == "__main__":
    unittest.main()
