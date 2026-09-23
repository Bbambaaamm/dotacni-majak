import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "mmr" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_mmr import MmrAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


FIX = ROOT / "connectors" / "mmr" / "fixtures"
INDEX = (FIX / "index.html").read_text(encoding="utf-8")
CATEGORY = (FIX / "category.html").read_text(encoding="utf-8")
NNO = (FIX / "nno-index.html").read_text(encoding="utf-8")
DETAIL = (FIX / "detail-117d75.html").read_text(encoding="utf-8")
NNO_DETAIL = (FIX / "detail-nno.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class MmrAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/cs/narodni-dotace":
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"}, request=request)
        if path == "/cs/narodni-dotace/podpora-a-rozvoj-regionu":
            return httpx.Response(200, text=CATEGORY, headers={"content-type": "text/html"}, request=request)
        if path == "/cs/narodni-dotace/dotace-pro-nestatni-neziskove-organizace":
            return httpx.Response(200, text=NNO, headers={"content-type": "text/html"}, request=request)
        if path.endswith("obnova-nemeckych-hrobu-2026"):
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"}, request=request)
        if path.endswith("dotace-pro-nestatni-neziskove-organizace-2026-3-vy"):
            return httpx.Response(200, text=NNO_DETAIL, headers={"content-type": "text/html"}, request=request)
        if path.startswith("/getmedia/"):
            mime = "application/pdf" if ".pdf" in str(request.url) else (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if path.endswith(".docx")
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            return httpx.Response(200, content=b"fixture", headers={"content-type": mime}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = MmrAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="mmr-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_is_bounded_and_excludes_results_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()
        self.assertEqual(page.total_hint, 2)
        ids = {item.external_id for item in page.items}
        self.assertIn("MMR-1-2026-117D75", ids)
        self.assertTrue(any("NNO" in value for value in ids))
        self.assertFalse(any("2025" in (item.title_hint or "") for item in page.items))

    async def test_detail_extracts_updated_deadline_and_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "MMR-1-2026-117D75")
                record = (await adapter.fetch_record(ctx, item)).record
                call_doc = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                artifact = await adapter.fetch_artifact(ctx, call_doc)
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["callCode"], "1/2026/117D75")
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-10-07"))
        self.assertIn("obec", record.raw_fields["eligibleApplicantsText"])
        self.assertIn("obnova", record.raw_fields["supportedActivitiesText"].casefold())
        self.assertEqual(
            {a.role for a in record.artifacts},
            {"CALL_DOCUMENT", "APPLICATION_FORM", "GUIDELINES"},
        )
        self.assertTrue(artifact.snapshot_id)

    async def test_nno_call_is_discovered_as_distinct_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if "NNO" in i.external_id)
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["callCode"], "3/2026/NNO")
        self.assertIn("neziskové organizace", record.raw_fields["eligibleApplicantsText"])
        self.assertTrue(record.snapshot_ids)


if __name__ == "__main__":
    unittest.main()
