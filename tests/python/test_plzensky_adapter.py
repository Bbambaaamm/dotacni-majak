import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "plzensky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_plzensky import PlzenskyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


INDEX = (ROOT / "connectors" / "plzensky" / "fixtures" / "index.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "plzensky" / "fixtures" / "detail.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class PlzenskyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/verejnost":
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"}, request=request)
        if path in {"/verejnost/dotacnititul/1589", "/verejnost/dotacnititul/1593"}:
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html; charset=utf-8"}, request=request)
        if "/soubor/" in path:
            return httpx.Response(200, content=b"%PDF-fixture", headers={"content-type": "application/pdf"}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = PlzenskyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="plzensky-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_uses_numeric_title_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()
        self.assertEqual(health.status.value, "HEALTHY")
        self.assertEqual(page.total_hint, 2)
        self.assertEqual({x.external_id for x in page.items}, {"PLK-1589", "PLK-1593"})

    async def test_detail_extracts_dates_finance_applicants_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(x for x in page.items if x.external_id == "PLK-1589")
                result = await adapter.fetch_record(ctx, item)
                record = result.record
                artifact = await adapter.fetch_artifact(ctx, record.artifacts[0])
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertTrue(record.raw_fields["submissionOpenAt"].startswith("2026-05-31T22:00:01"))
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2027-03-31T21:59:59"))
        self.assertEqual(record.raw_fields["totalAllocationMinor"], 1274510500)
        self.assertEqual(record.raw_fields["grantAmountMaxMinor"], 150000000)
        self.assertEqual(record.raw_fields["regionCode"], "CZ032")
        self.assertIn("Školy", record.raw_fields["eligibleApplicantsText"])
        self.assertEqual(len(record.artifacts), 2)
        self.assertTrue(record.snapshot_ids)
        self.assertTrue(artifact.snapshot_id)


if __name__ == "__main__":
    unittest.main()
