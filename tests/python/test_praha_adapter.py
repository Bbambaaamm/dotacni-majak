import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "praha" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_praha import PrahaAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


RSS = (ROOT / "connectors" / "praha" / "fixtures" / "granty-rss.xml").read_bytes()
DETAIL = (ROOT / "connectors" / "praha" / "fixtures" / "detail-sport.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class PrahaAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/pub/rss/"):
            return httpx.Response(
                200,
                content=RSS,
                headers={"content-type": "application/rss+xml"},
                request=request,
            )
        if request.url.path == "/pub/deska/detail-sport":
            return httpx.Response(
                200,
                text=DETAIL,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if request.url.path == "/pub/deska/detail-zp":
            return httpx.Response(
                200,
                text=DETAIL.replace("sportu", "životního prostředí"),
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if request.url.path.startswith("/files/"):
            mime = (
                "application/pdf"
                if request.url.path.endswith(".pdf")
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            return httpx.Response(200, content=b"fixture", headers={"content-type": mime}, request=request)
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        adapter = PrahaAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return adapter, client, AdapterContext(
            run_id="praha-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_uses_rss_and_excludes_admin_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(health.status.value, "HEALTHY")
        self.assertEqual(page.total_hint, 2)
        ids = {item.external_id for item in page.items}
        self.assertIn("PRAHA-929435-2026", ids)
        self.assertIn("PRAHA-867920-2026", ids)
        self.assertNotIn("PRAHA-895573-2026", ids)

    async def test_detail_extracts_only_explicit_application_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = await self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "PRAHA-929435-2026")
                result = await adapter.fetch_record(ctx, item)
                record = result.record
                call_doc = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                artifact = await adapter.fetch_artifact(ctx, call_doc)
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "PLANNED")
        self.assertTrue(record.raw_fields["submissionOpenAt"].startswith("2026-10-14T22:00:00"))
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-10-31T22:59:59"))
        self.assertEqual(record.raw_fields["regionCode"], "CZ010")
        self.assertEqual(record.raw_fields["noticeNumber"], "MHMP 929435/2026")
        self.assertEqual(len(record.artifacts), 2)
        self.assertTrue(record.snapshot_ids)
        self.assertTrue(artifact.snapshot_id)

    async def test_rss_rejects_dtd_entities(self):
        evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY x "boom">]><rss><channel/></rss>'

        def evil_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=evil,
                headers={"content-type": "application/rss+xml"},
                request=request,
            )

        with tempfile.TemporaryDirectory() as tmp:
            adapter = PrahaAdapter()
            client = GuardedHttpClient(
                allowed_hosts=set(adapter.descriptor.allowed_hosts),
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(evil_handler),
            )
            ctx = AdapterContext(
                run_id="evil",
                http=client,
                logger=None,
                budget=None,
                snapshots=LocalRawSnapshotStore(tmp),
                now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
            )
            try:
                with self.assertRaises(ValueError):
                    await adapter.discover(ctx, None)
            finally:
                await client.aclose()


if __name__ == "__main__":
    unittest.main()
