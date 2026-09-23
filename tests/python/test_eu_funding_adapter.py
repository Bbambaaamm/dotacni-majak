import asyncio
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "eu-funding" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_eu_funding.adapter import EuFundingTendersAdapter
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


FIXTURE = ROOT / "connectors" / "eu-funding" / "fixtures" / "search-page-1.json"


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class EuFundingAdapterTest(unittest.IsolatedAsyncioTestCase):
    def fixture_payload(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    async def test_discovery_parses_real_contract_and_filters_stale_open(self):
        payload = self.fixture_payload()

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            return httpx.Response(200, json=payload, request=request)

        with tempfile.TemporaryDirectory() as tmp:
            client = GuardedHttpClient(
                allowed_hosts={"api.tech.ec.europa.eu", "ec.europa.eu"},
                allowed_post_paths={"/search-api/prod/rest/search"},
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="r1",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=LocalRawSnapshotStore(tmp),
                    now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
                )
                page = await EuFundingTendersAdapter(page_size=2).discover(
                    ctx,
                    None,
                )
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 1211)
        self.assertEqual(len(page.items), 1)
        item = page.items[0]
        self.assertEqual(item.external_id, "ISF-2026-TF2-AG-CORRUPT")
        self.assertEqual(item.native_status_hint, "31094502")
        self.assertIn("discovery_snapshot_id", item.metadata)
        self.assertFalse(page.is_complete)
        self.assertEqual(page.next_checkpoint.cursor, "2")

    async def test_fetch_record_creates_raw_snapshot_and_discovers_call_pdf(self):
        payload = self.fixture_payload()
        first_only = {**payload, "results": [payload["results"][0]]}

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=first_only,
                headers={"content-type": "application/json"},
                request=request,
            )

        with tempfile.TemporaryDirectory() as tmp:
            client = GuardedHttpClient(
                allowed_hosts={"api.tech.ec.europa.eu", "ec.europa.eu"},
                allowed_post_paths={"/search-api/prod/rest/search"},
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="r2",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=LocalRawSnapshotStore(tmp),
                    now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
                )
                adapter = EuFundingTendersAdapter()
                item = (await adapter.discover(ctx, None)).items[0]
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        self.assertEqual(result.state.value, "MODIFIED")
        self.assertIsNotNone(result.record)
        self.assertEqual(
            result.record.external_id,
            "ISF-2026-TF2-AG-CORRUPT",
        )
        self.assertTrue(result.record.snapshot_ids)
        self.assertEqual(len(result.record.artifacts), 1)
        self.assertEqual(result.record.artifacts[0].role, "CALL_DOCUMENT")
        self.assertTrue(
            str(result.record.artifacts[0].url).endswith(
                "call-fiche_isf-2026-tf2-ag-corrupt_en.pdf"
            )
        )
        self.assertIsInstance(
            result.record.raw_fields["budgetOverviewParsed"],
            dict,
        )

    async def test_fetch_artifact_is_snapshotted(self):
        pdf_bytes = b"%PDF-1.7 fixture"

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=pdf_bytes,
                headers={"content-type": "application/pdf"},
                request=request,
            )

        payload = self.fixture_payload()
        first_only = {**payload, "results": [payload["results"][0]]}

        # Use the adapter's discovered artifact from the real-contract fixture.
        async def detail_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(".pdf"):
                return await handler(request)
            return httpx.Response(
                200,
                json=first_only,
                headers={"content-type": "application/json"},
                request=request,
            )

        with tempfile.TemporaryDirectory() as tmp:
            client = GuardedHttpClient(
                allowed_hosts={"api.tech.ec.europa.eu", "ec.europa.eu"},
                allowed_post_paths={"/search-api/prod/rest/search"},
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(detail_handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="r3",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=LocalRawSnapshotStore(tmp),
                    now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
                )
                adapter = EuFundingTendersAdapter()
                item = (await adapter.discover(ctx, None)).items[0]
                record = (await adapter.fetch_record(ctx, item)).record
                result = await adapter.fetch_artifact(
                    ctx,
                    record.artifacts[0],
                )
            finally:
                await client.aclose()

        self.assertEqual(result.state.value, "MODIFIED")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.size_bytes, len(pdf_bytes))
        self.assertTrue(result.snapshot_id)


if __name__ == "__main__":
    unittest.main()
