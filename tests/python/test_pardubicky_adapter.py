import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "pardubicky" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_pardubicky import PardubickyAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


INDEX = (ROOT / "connectors" / "pardubicky" / "fixtures" / "index.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "pardubicky" / "fixtures" / "detail.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class PardubickyAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/grants":
            return httpx.Response(
                200,
                text=INDEX,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if path.startswith("/grants/"):
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
        adapter = PardubickyAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="pardubicky-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_uses_public_uuid_identity_and_card_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(health.status.value, "HEALTHY")
        self.assertEqual(page.total_hint, 2)
        c1 = next(item for item in page.items if item.external_id.startswith("PAK-5c9fdbdb"))
        self.assertEqual(c1.native_status_hint, "CLOSED")
        self.assertTrue(c1.metadata["submission_open_at"].startswith("2025-12-31T23:00:00"))
        self.assertTrue(c1.metadata["submission_close_at"].startswith("2026-02-02T22:59:59"))

    async def test_detail_extracts_applicants_finance_and_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                c1 = next(item for item in page.items if item.external_id.startswith("PAK-5c9fdbdb"))
                record = (await adapter.fetch_record(ctx, c1)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["regionCode"], "CZ053")
        self.assertIn("sportovní kluby", record.raw_fields["eligibleApplicantsText"])
        self.assertIn("Obec", record.raw_fields["eligibleApplicantsText"])
        self.assertEqual(record.raw_fields["grantAmountMinMinor"], 5_000_000)
        self.assertEqual(record.raw_fields["grantAmountMaxMinor"], 75_000_000)
        self.assertIsNone(record.raw_fields["ownContributionMinBps"])
        self.assertIn("30 %", record.raw_fields["ownContributionText"])
        self.assertIn("50 %", record.raw_fields["ownContributionText"])
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-02-02T11:00:00"))
        self.assertTrue(record.raw_fields["applicationUrl"])
        self.assertTrue(record.snapshot_ids)

    async def test_legacy_numeric_detail_id_is_discoverable(self):
        html = """<html><body><div><h3>Historický program</h3>
        <a href="/grants/660030553">Přejít na detail</a></div></body></html>"""
        with tempfile.TemporaryDirectory() as tmp:
            adapter = PardubickyAdapter()
            client = GuardedHttpClient(
                allowed_hosts=set(adapter.descriptor.allowed_hosts),
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        text=html,
                        headers={"content-type": "text/html"},
                        request=request,
                    )
                ),
            )
            ctx = AdapterContext(
                run_id="legacy-id-test",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
            )
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()
        self.assertEqual(page.items[0].external_id, "PAK-660030553")

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
