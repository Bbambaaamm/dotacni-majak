import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "opzp" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_opzp import OpzpAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


LISTING = (
    ROOT / "connectors" / "opzp" / "fixtures" / "listing.html"
).read_text(encoding="utf-8")
DETAIL = (
    ROOT / "connectors" / "opzp" / "fixtures" / "call-108.html"
).read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class OpzpAdapterTest(unittest.IsolatedAsyncioTestCase):
    def make_handler(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path.rstrip("/")
            if path == "/nabidka-dotaci":
                return httpx.Response(
                    200,
                    text=LISTING,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path == "/dotace/108-vyzva":
                return httpx.Response(
                    200,
                    text=DETAIL,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path.startswith("/files/documents/"):
                return httpx.Response(
                    200,
                    content=b"%PDF-1.7 OPZP fixture",
                    headers={"content-type": "application/pdf"},
                    request=request,
                )
            return httpx.Response(404, request=request)

        return handler

    async def make_context(self, tmp):
        client = GuardedHttpClient(
            allowed_hosts={
                "opzp.cz",
                "www.opzp.cz",
                "2021-2027.opzp.cz",
            },
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.make_handler()),
        )
        ctx = AdapterContext(
            run_id="opzp-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
        )
        return client, ctx

    async def test_discovery_parses_and_deduplicates_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.make_context(tmp)
            try:
                page = await OpzpAdapter().discover(ctx, None)
            finally:
                await client.aclose()

        self.assertTrue(page.is_complete)
        self.assertEqual(page.total_hint, 2)
        self.assertEqual(
            [item.external_id for item in page.items],
            ["OPZP-108", "OPZP-109"],
        )
        self.assertTrue(
            all("listing_snapshot_id" in item.metadata for item in page.items)
        )

    async def test_detail_parses_core_fields_and_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.make_context(tmp)
            try:
                adapter = OpzpAdapter()
                page = await adapter.discover(ctx, None)
                item = next(
                    candidate
                    for candidate in page.items
                    if candidate.external_id == "OPZP-108"
                )
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["allocationCzk"], 60_000_000)
        self.assertEqual(record.raw_fields["callType"], "Průběžná")
        self.assertEqual(len(record.raw_fields["applicants"]), 4)
        self.assertIn(
            "Veřejnoprávní instituce",
            record.raw_fields["applicants"],
        )
        self.assertIsNotNone(record.raw_fields["submissionOpenAt"])
        self.assertIsNotNone(record.raw_fields["submissionCloseAt"])
        self.assertTrue(record.snapshot_ids)
        self.assertEqual(len(record.artifacts), 2)
        self.assertEqual(
            {artifact.role for artifact in record.artifacts},
            {"CALL_DOCUMENT", "GUIDELINES"},
        )

    async def test_artifact_is_snapshotted(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.make_context(tmp)
            try:
                adapter = OpzpAdapter()
                page = await adapter.discover(ctx, None)
                item = next(
                    candidate
                    for candidate in page.items
                    if candidate.external_id == "OPZP-108"
                )
                record = (await adapter.fetch_record(ctx, item)).record
                artifact = next(
                    document
                    for document in record.artifacts
                    if document.role == "CALL_DOCUMENT"
                )
                result = await adapter.fetch_artifact(ctx, artifact)
            finally:
                await client.aclose()

        self.assertEqual(result.state.value, "MODIFIED")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertTrue(result.snapshot_id)
        self.assertGreater(result.size_bytes or 0, 0)


if __name__ == "__main__":
    unittest.main()
