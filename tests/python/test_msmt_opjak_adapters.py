import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "msmt" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_msmt import MsmtAdapter, OpJakAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


MSMT_LISTING = (
    ROOT / "connectors" / "msmt" / "fixtures" / "msmt-listing.html"
).read_text(encoding="utf-8")
MSMT_DETAIL = (
    ROOT / "connectors" / "msmt" / "fixtures" / "msmt-detail.html"
).read_text(encoding="utf-8")
OPJAK_LISTING = (
    ROOT / "connectors" / "msmt" / "fixtures" / "opjak-listing.html"
).read_text(encoding="utf-8")
OPJAK_DETAIL = (
    ROOT / "connectors" / "msmt" / "fixtures" / "opjak-detail.html"
).read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class MsmtOpJakAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path.rstrip("/")

        if host in {"msmt.gov.cz", "www.msmt.gov.cz"}:
            if path == "/dotace":
                return httpx.Response(
                    200,
                    text=MSMT_LISTING,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path.startswith("/dotace/"):
                return httpx.Response(
                    200,
                    text=MSMT_DETAIL,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path.startswith("/files/"):
                mime = (
                    "application/pdf"
                    if path.endswith(".pdf")
                    else (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        if path.endswith(".xlsx")
                        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                )
                return httpx.Response(
                    200, content=b"fixture", headers={"content-type": mime}, request=request
                )

        if host in {"opjak.cz", "www.opjak.cz"}:
            if path == "/vyzvy":
                return httpx.Response(
                    200,
                    text=OPJAK_LISTING,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path.startswith("/vyzvy/vyzva-"):
                return httpx.Response(
                    200,
                    text=OPJAK_DETAIL,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path.startswith("/wp-content/uploads/"):
                mime = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if path.endswith(".xlsx")
                    else "application/pdf"
                )
                return httpx.Response(
                    200, content=b"fixture", headers={"content-type": mime}, request=request
                )

        return httpx.Response(404, request=request)

    async def context(self, tmp, adapter):
        client = GuardedHttpClient(
            allowed_hosts=set(adapter.descriptor.allowed_hosts),
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return client, AdapterContext(
            run_id="msmt-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_msmt_discovery_filters_supplementary_articles(self):
        adapter = MsmtAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp, adapter)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 2)
        ids = {item.external_id for item in page.items}
        self.assertIn("MSMT-630-2026-3", ids)
        self.assertFalse(any("dodatek" in item.title_hint.casefold() for item in page.items))

    async def test_msmt_detail_extracts_status_audience_deadline_and_artifacts(self):
        adapter = MsmtAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp, adapter)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "MSMT-630-2026-3")
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["projectType"], "Neinvestiční")
        self.assertIn("Církevní školy", record.raw_fields["eligibleApplicantsText"])
        self.assertTrue(record.raw_fields["submissionCloseAt"].startswith("2026-10-31"))
        self.assertEqual(
            {artifact.role for artifact in record.artifacts},
            {"CALL_DOCUMENT", "APPLICATION_FORM", "ANNEX"},
        )

    async def test_opjak_discovery_extracts_call_code_dates_and_allocation(self):
        adapter = OpJakAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp, adapter)
            try:
                page = await adapter.discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 2)
        ai = next(i for i in page.items if i.external_id == "OPJAK-02_26_048")
        self.assertEqual(ai.metadata["allocationCzk"], 300_000_000)
        self.assertTrue(ai.metadata["submissionCloseAt"].startswith("2026-12-30"))

    async def test_opjak_detail_extracts_decision_fields_and_documents(self):
        adapter = OpJakAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp, adapter)
            try:
                page = await adapter.discover(ctx, None)
                item = next(i for i in page.items if i.external_id == "OPJAK-02_26_048")
                record = (await adapter.fetch_record(ctx, item)).record
                call_document = next(
                    artifact for artifact in record.artifacts
                    if artifact.role == "CALL_DOCUMENT"
                )
                artifact_result = await adapter.fetch_artifact(ctx, call_document)
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertEqual(record.raw_fields["callCode"], "02_26_048")
        self.assertEqual(record.raw_fields["allocationCzk"], 300_000_000)
        self.assertIn("umělé inteligence", record.raw_fields["supportedActivitiesText"])
        self.assertIn("Veřejné vysoké školy", record.raw_fields["eligibleApplicantsText"])
        self.assertIn("ISKP21+", record.raw_fields["applicationMethodText"])
        self.assertEqual(
            {artifact.role for artifact in record.artifacts},
            {"CALL_DOCUMENT", "ANNEX", "GUIDELINES"},
        )
        self.assertTrue(artifact_result.snapshot_id)


if __name__ == "__main__":
    unittest.main()
