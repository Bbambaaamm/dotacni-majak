import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "mk" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_mk import MkAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


INDEX = (ROOT / "connectors" / "mk" / "fixtures" / "index.html").read_text(encoding="utf-8")
ANNUAL = (ROOT / "connectors" / "mk" / "fixtures" / "annual-index.html").read_text(encoding="utf-8")
CALL_2521 = (ROOT / "connectors" / "mk" / "fixtures" / "call-2521.html").read_text(encoding="utf-8")
CREATIVE = (ROOT / "connectors" / "mk" / "fixtures" / "call-creative-europe.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class MkAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/granty-a-dotace-cs-1234":
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"}, request=request)
        if path == "/vyberova-dotacni-rizeni-na-rok-2026-vyhlaseni":
            return httpx.Response(200, text=ANNUAL, headers={"content-type": "text/html"}, request=request)
        if path.endswith("vyzva-c-2521-audiovize-a-media-k-predkladani-zadosti-o-poskytnuti-dotace-v-programu-kulturni-aktivity"):
            return httpx.Response(200, text=CALL_2521, headers={"content-type": "text/html"}, request=request)
        if path == "/zadost-o-dotaci-ze-statniho-rozpoctu-v-roce-2026":
            return httpx.Response(200, text=CREATIVE, headers={"content-type": "text/html"}, request=request)
        if path.startswith("/doc/"):
            mime = (
                "application/pdf" if path.endswith(".pdf")
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if path.endswith((".xlsx", ".xlsm"))
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            return httpx.Response(200, content=b"fixture", headers={"content-type": mime}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = MkAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="mk-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_follows_index_but_excludes_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 2)
        ids = {item.external_id for item in page.items}
        self.assertIn("MK-2521", ids)
        self.assertTrue(any("zadost-o-dotaci" in i for i in ids))
        self.assertFalse(any("vysled" in (item.title_hint or "").casefold() for item in page.items))

    async def test_call_2521_extracts_deadline_applicants_and_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "MK-2521")
                record = (await adapter.fetch_record(ctx, item)).record
                call_doc = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                artifact = await adapter.fetch_artifact(ctx, call_doc)
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["callCode"], "2521")
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2025-10-31"))
        self.assertIn("právnické a fyzické osoby", record.raw_fields["eligibleApplicantsText"])
        self.assertIn("Dotačního portálu", record.raw_fields["applicationMethodText"])
        self.assertEqual(
            {a.role for a in record.artifacts},
            {"CALL_DOCUMENT", "ANNEX", "GUIDELINES"},
        )
        self.assertTrue(artifact.snapshot_id)

    async def test_creative_europe_is_single_call_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if "zadost-o-dotaci" in i.external_id)
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-09-16"))
        self.assertIn("Kreativní Evropa", record.raw_fields["supportedActivitiesText"])
        self.assertIn("fyzické osoby", record.raw_fields["eligibleApplicantsText"])
        self.assertTrue(record.snapshot_ids)


if __name__ == "__main__":
    unittest.main()
