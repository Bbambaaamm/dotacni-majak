import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "vysocina" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient
from dotacni_majak_vysocina import VysocinaAdapter


INDEX = (ROOT / "connectors" / "vysocina" / "fixtures" / "index.html").read_text(
    encoding="utf-8"
)
INDEX_2 = (
    ROOT / "connectors" / "vysocina" / "fixtures" / "index-page-2.html"
).read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "vysocina" / "fixtures" / "detail.html").read_text(
    encoding="utf-8"
)


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class VysocinaAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/vismo/rejstrik.asp" in request.url.path:
            body = INDEX_2 if "stranka=2" in url else INDEX
            return httpx.Response(
                200,
                text=body,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if "/d-" in request.url.path:
            return httpx.Response(
                200,
                text=DETAIL,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if "/assets/File.ashx" in request.url.path:
            return httpx.Response(
                200,
                content=b"%PDF-fixture",
                headers={"content-type": "application/pdf"},
                request=request,
            )
        return httpx.Response(404, request=request)

    def context(self, tmp):
        adapter = VysocinaAdapter()
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        ctx = AdapterContext(
            run_id="vys-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        return adapter, client, ctx

    async def test_discovery_keeps_announcements_and_excludes_award_news(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        ids = {item.external_id for item in page.items}
        self.assertEqual(ids, {"VYS-4136309", "VYS-4136395"})
        self.assertNotIn("VYS-4999999", ids)
        self.assertTrue(
            all(
                item.metadata["coverage"] == "LIMITED_OFFICIAL_ANNOUNCEMENTS"
                for item in page.items
            )
        )

    async def test_detail_parses_application_window_and_same_origin_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                page = await adapter.discover(ctx, None)
                item = next(
                    item for item in page.items
                    if item.external_id == "VYS-4136309"
                )
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(
            record.raw_fields["submissionOpenAt"],
            "2026-03-22T23:00:00+00:00",
        )
        self.assertEqual(
            record.raw_fields["submissionCloseAt"],
            "2026-04-17T10:00:00+00:00",
        )
        self.assertEqual(record.raw_fields["regionCode"], "CZ063")
        self.assertEqual(
            record.raw_fields["coverage"],
            "LIMITED_OFFICIAL_ANNOUNCEMENTS",
        )
        self.assertEqual(len(record.artifacts), 1)
        self.assertIn("assets/File.ashx", str(record.artifacts[0].url))
        self.assertTrue(record.snapshot_ids)

    async def test_artifact_is_raw_backed(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                item = (await adapter.discover(ctx, None)).items[0]
                record = (await adapter.fetch_record(ctx, item)).record
                artifact = await adapter.fetch_artifact(ctx, record.artifacts[0])
            finally:
                await client.aclose()
        self.assertEqual(artifact.state.value, "MODIFIED")
        self.assertTrue(artifact.snapshot_id)

    async def test_health_uses_public_official_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, client, ctx = self.context(tmp)
            try:
                health = await adapter.healthcheck(ctx)
            finally:
                await client.aclose()
        self.assertEqual(health.status.value, "HEALTHY")


if __name__ == "__main__":
    unittest.main()
