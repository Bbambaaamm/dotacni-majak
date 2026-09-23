import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "mze" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_mze import MzeSzifAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


INDEX = (ROOT / "connectors" / "mze" / "fixtures" / "national-index.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "mze" / "fixtures" / "nno-2027.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class MzeSzifAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/public/portal/mze/vyhledavani/narodni-dotace":
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"}, request=request)
        if path.endswith("/vyzva-k-podani-zadosti-nno-2027"):
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"}, request=request)
        if path.startswith("/public/web/file/") or path == "/cs/CmDocument":
            content_type = "application/pdf" if "pdf" in str(request.url).casefold() else "application/octet-stream"
            return httpx.Response(200, content=b"fixture-document", headers={"content-type": content_type}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = MzeSzifAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="mze-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_is_conservative_and_excludes_results_and_guidelines(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 1)
        self.assertEqual(page.items[0].external_id, "MZE-NNO-2027")
        self.assertIn("nestátních neziskových", page.items[0].title_hint)

    async def test_nno_2027_extracts_deadline_applicants_support_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                record = (await adapter.fetch_record(ctx, page.items[0])).record
                szif = next(a for a in record.artifacts if "szif.gov.cz" in str(a.url))
                artifact = await adapter.fetch_artifact(ctx, szif)
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-09-30T11:00:00"))
        self.assertIn("Nestátní neziskové organizace", record.raw_fields["eligibleApplicantsText"])
        self.assertIn("Ministerstva zemědělství", record.raw_fields["supportedActivitiesText"])
        self.assertIn("datové schránky", record.raw_fields["applicationMethodText"])
        self.assertEqual(
            {a.role for a in record.artifacts},
            {"CALL_DOCUMENT", "GUIDELINES", "ANNEX"},
        )
        self.assertTrue(record.snapshot_ids)
        self.assertTrue(artifact.snapshot_id)

    async def test_coverage_note_discloses_captcha_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                record = (await adapter.fetch_record(ctx, page.items[0])).record
            finally:
                await client.aclose()

        self.assertIn("CAPTCHA", record.raw_fields["coverageNote"])
        self.assertIn("není obcházen", record.raw_fields["coverageNote"])


if __name__ == "__main__":
    unittest.main()
