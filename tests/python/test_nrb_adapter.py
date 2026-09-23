import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "nrb" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_nrb import NrbAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


def fixture(name):
    return (ROOT / "connectors" / "nrb" / "fixtures" / name).read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class NrbAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        mapping = {
            "/podnikatele/uvery": "loans.html",
            "/podnikatele/zaruky": "guarantees.html",
            "/produkt/narodni-zaruka": "national-guarantee.html",
            "/produkt/nove-uspory-energie": "energy-savings.html",
            "/produkt/uver-expanze": "expansion.html",
            "/produkt/novy-energ": "expansion.html",
        }
        if path in mapping:
            return httpx.Response(
                200,
                text=fixture(mapping[path]),
                headers={"content-type": "text/html"},
                request=request,
            )
        if path.startswith("/wp-content/uploads/"):
            return httpx.Response(
                200,
                content=b"official-document",
                headers={"content-type": "application/pdf"},
                request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = NrbAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="nrb-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_merges_product_identity_across_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()
        self.assertEqual(page.total_hint, 4)
        self.assertTrue(any(item.external_id == "NRB-narodni-zaruka" for item in page.items))

    async def test_guarantee_is_not_a_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "NRB-narodni-zaruka")
                record = (await adapter.fetch_record(ctx, item)).record
                call_doc = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                artifact = await adapter.fetch_artifact(ctx, call_doc)
            finally:
                await client.aclose()

        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["fundingInstrumentType"], "GUARANTEE")
        self.assertEqual(record.raw_fields["guaranteeCoverageBps"], 7000)
        self.assertEqual(record.raw_fields["loanAmountMinMinor"], 50_000_000)
        self.assertEqual(record.raw_fields["loanAmountMaxMinor"], 2_000_000_000)
        self.assertTrue(artifact.snapshot_id)

    async def test_loan_with_financial_contribution_is_mixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "NRB-nove-uspory-energie")
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["fundingInstrumentType"], "MIXED")
        self.assertEqual(record.raw_fields["interestRateBps"], 0)
        self.assertTrue(any("20 %" in text for text in record.raw_fields["contributionTexts"]))

    async def test_paused_loan_stays_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "NRB-uver-expanze")
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertEqual(record.native_status, "PAUSED")
        self.assertEqual(record.raw_fields["fundingInstrumentType"], "LOAN")
        self.assertEqual(record.raw_fields["interestRateBps"], 0)
        self.assertIn("15 let", record.raw_fields["maturityText"])


if __name__ == "__main__":
    unittest.main()
