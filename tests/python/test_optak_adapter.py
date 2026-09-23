import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "optak" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_optak import OpTakAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


LISTING = (ROOT / "connectors" / "optak" / "fixtures" / "listing.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "connectors" / "optak" / "fixtures" / "poradenstvi-iii.html").read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class OpTakAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path == "/cs/radce/vsechny-vyzvy":
            return httpx.Response(
                200, text=LISTING,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path.endswith("/poradenstvi-vyzva-iii"):
            return httpx.Response(
                200, text=DETAIL,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path.startswith("/wp-content/uploads/"):
            mime = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if path.endswith(".docx") else "application/pdf"
            )
            return httpx.Response(
                200, content=b"fixture document",
                headers={"content-type": mime}, request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        client = GuardedHttpClient(
            allowed_hosts={"apiagentura.gov.cz", "www.apiagentura.gov.cz"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return client, AdapterContext(
            run_id="optak-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_listing_discovers_open_and_closed_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                page = await OpTakAdapter().discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 3)
        statuses = {item.title_hint: item.native_status_hint for item in page.items}
        self.assertEqual(statuses["Poradenství – výzva III"], "OPEN")
        self.assertEqual(
            statuses["Partnerství znalostního transferu – výzva IV"],
            "CLOSED",
        )
        item = next(i for i in page.items if i.title_hint == "Poradenství – výzva III")
        self.assertEqual(item.metadata["activityFocus"], "poradenské služby pro MSP")
        self.assertTrue(item.metadata["submissionCloseAt"])

    async def test_detail_extracts_decision_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = OpTakAdapter()
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.title_hint == "Poradenství – výzva III")
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertIn("malé a střední podniky", record.raw_fields["eligibleApplicantsText"])
        self.assertEqual(record.raw_fields["supportRateMaxPercent"], 50.0)
        self.assertEqual(record.raw_fields["projectCostMinCzk"], 100_000)
        self.assertEqual(record.raw_fields["projectCostMaxCzk"], 4_900_000)
        self.assertIn("mimo NUTS 2 Praha", record.raw_fields["restrictionsText"])
        self.assertEqual(
            {artifact.role for artifact in record.artifacts},
            {"CALL_DOCUMENT", "GUIDELINES", "ANNEX"},
        )

    async def test_artifact_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = OpTakAdapter()
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.title_hint == "Poradenství – výzva III")
                record = (await adapter.fetch_record(ctx, item)).record
                artifact = next(a for a in record.artifacts if a.role == "CALL_DOCUMENT")
                result = await adapter.fetch_artifact(ctx, artifact)
            finally:
                await client.aclose()
        self.assertTrue(result.snapshot_id)
        self.assertGreater(result.size_bytes or 0, 0)


if __name__ == "__main__":
    unittest.main()
