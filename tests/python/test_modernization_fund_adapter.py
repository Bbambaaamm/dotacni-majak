import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "modernization-fund" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_modernization_fund import ModernizationFundAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


LISTING = (
    ROOT / "connectors" / "modernization-fund" / "fixtures" / "listing.html"
).read_text(encoding="utf-8")
DETAIL = (
    ROOT / "connectors" / "modernization-fund" / "fixtures" / "call-53.html"
).read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class ModernizationFundAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/dotace-a-pujcky/modernizacni-fond/vyzvy":
            return httpx.Response(
                200,
                text=LISTING,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path == "/dotace-a-pujcky/modernizacni-fond/vyzvy/detail-vyzvy":
            return httpx.Response(
                200,
                text=DETAIL,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path.startswith("/files/documents/"):
            return httpx.Response(
                200,
                content=b"%PDF-1.7 Modernisation Fund fixture",
                headers={"content-type": "application/pdf"},
                request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        client = GuardedHttpClient(
            allowed_hosts={
                "sfzp.gov.cz",
                "www.sfzp.gov.cz",
                "sfzp.cz",
                "www.sfzp.cz",
            },
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        ctx = AdapterContext(
            run_id="modf-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        return client, ctx

    async def test_discovers_server_rendered_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                page = await ModernizationFundAdapter().discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 2)
        self.assertEqual(
            [item.external_id for item in page.items],
            ["MODF-52", "MODF-53"],
        )
        self.assertTrue(
            all("listing_snapshot_id" in item.metadata for item in page.items)
        )

    async def test_detail_extracts_eligibility_finance_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = ModernizationFundAdapter()
                page = await adapter.discover(ctx, None)
                item = next(
                    candidate
                    for candidate in page.items
                    if candidate.external_id == "MODF-53"
                )
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["supportRateMaxPercent"], 30.0)
        self.assertEqual(record.raw_fields["allocationCzk"], 300_000_000)
        self.assertIn("Zemědělští podnikatelé", record.raw_fields["eligibleApplicantsText"])
        self.assertIn("agrofotovoltaických", record.raw_fields["supportedActivitiesText"])
        self.assertTrue(record.raw_fields["submissionOpenAt"].endswith("+00:00"))
        self.assertTrue(record.raw_fields["submissionCloseAt"].endswith("+00:00"))
        self.assertEqual(
            {artifact.role for artifact in record.artifacts},
            {"CALL_DOCUMENT", "GUIDELINES"},
        )

    async def test_call_document_is_snapshotted(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = ModernizationFundAdapter()
                page = await adapter.discover(ctx, None)
                record = (
                    await adapter.fetch_record(
                        ctx,
                        next(item for item in page.items if item.external_id == "MODF-53"),
                    )
                ).record
                artifact = next(
                    item for item in record.artifacts if item.role == "CALL_DOCUMENT"
                )
                result = await adapter.fetch_artifact(ctx, artifact)
            finally:
                await client.aclose()

        self.assertEqual(result.state.value, "MODIFIED")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertTrue(result.snapshot_id)


if __name__ == "__main__":
    unittest.main()
