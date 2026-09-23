import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "khk" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_khk import KhkAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


COLLECTION = json.loads(
    (ROOT / "connectors" / "khk" / "fixtures" / "collection.json")
    .read_text(encoding="utf-8")
)
DETAIL = json.loads(
    (ROOT / "connectors" / "khk" / "fixtures" / "detail.json")
    .read_text(encoding="utf-8")
)
DOCUMENTS = json.loads(
    (ROOT / "connectors" / "khk" / "fixtures" / "documents.json")
    .read_text(encoding="utf-8")
)


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class KhkAdapterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.seen = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        payload = None
        if request.content:
            payload = json.loads(request.content.decode("utf-8"))
        self.seen.append((request.method, path, payload))

        if request.method == "GET" and request.url.host == "dotace.khk.cz":
            return httpx.Response(
                200,
                text="<html><title>Dotace KHK</title><body>Dotace KHK</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if path.endswith("/GetProjectSubprojectCollection"):
            return httpx.Response(
                200,
                json=COLLECTION,
                headers={"content-type": "application/json"},
                request=request,
            )
        if path.endswith("/GetSubprojectDocumentCollection"):
            return httpx.Response(
                200,
                json=DOCUMENTS,
                headers={"content-type": "application/json"},
                request=request,
            )
        if path.endswith("/GetSubproject"):
            return httpx.Response(
                200,
                json=DETAIL,
                headers={"content-type": "application/json"},
                request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = KhkAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            allowed_post_paths=set(adapter.descriptor.allowed_post_paths),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="khk-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_uses_verified_public_body_and_stable_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 2)
        investment = next(
            item for item in page.items
            if item.metadata["programCode"] == "26SPT10"
        )
        self.assertEqual(investment.external_id, "KHK-1156")
        self.assertEqual(
            str(investment.detail_url),
            "https://dotace.khk.cz/grantProgram/26SPT10",
        )
        self.assertEqual(investment.metadata["normalizedStatusHint"], "PLANNED")
        post = next(
            row for row in self.seen
            if row[1].endswith("/GetProjectSubprojectCollection")
        )
        self.assertEqual(post[2], {"year": ["2027", "2026"]})
        self.assertTrue(investment.metadata["discoverySnapshotId"])

    async def test_detail_normalizes_public_finance_and_applicants(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(
                    item for item in page.items
                    if item.metadata["programCode"] == "26SPT10"
                )
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.external_id, "KHK-1156")
        self.assertEqual(record.raw_fields["supportRateMaxBps"], 5000)
        self.assertEqual(record.raw_fields["grantAmountMinMinor"], 2_000_000)
        self.assertEqual(record.raw_fields["grantAmountMaxMinor"], 50_000_000)
        self.assertEqual(record.raw_fields["allocationMinor"], 700_000_000)
        self.assertIn(
            "Právnická osoba",
            record.raw_fields["eligibleApplicantsText"],
        )
        self.assertIn(
            "sportovní infrastruktury",
            record.raw_fields["purposeText"],
        )
        # November 2026 is CET (UTC+1)
        self.assertEqual(
            record.raw_fields["submissionOpenAt"],
            "2026-11-20T07:00:00+00:00",
        )
        self.assertEqual(
            record.raw_fields["submissionCloseAt"],
            "2026-12-11T11:00:00+00:00",
        )
        self.assertEqual(len(record.snapshot_ids), 3)

    async def test_document_collection_is_preserved_without_guessing_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                item = (await adapter.discover(ctx, None)).items[0]
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertEqual(len(record.raw_fields["documents"]), 2)
        self.assertEqual(record.raw_fields["documents"][0]["id"], 500001)
        self.assertEqual(
            record.raw_fields["documentCoverage"],
            "METADATA_ONLY_UNTIL_PUBLIC_DOWNLOAD_CONTRACT_VERIFIED",
        )
        self.assertEqual(record.artifacts, [])

    async def test_health_uses_public_portal_without_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
            finally:
                await client.aclose()
        self.assertEqual(health.status.value, "HEALTHY")


if __name__ == "__main__":
    unittest.main()
