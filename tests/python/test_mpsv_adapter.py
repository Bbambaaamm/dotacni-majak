import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "mpsv" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_mpsv import MpsvAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


FAMILY_INDEX = (
    ROOT / "connectors" / "mpsv" / "fixtures" / "family-index.html"
).read_text(encoding="utf-8")
SOCIAL_INDEX = (
    ROOT / "connectors" / "mpsv" / "fixtures" / "social-index.html"
).read_text(encoding="utf-8")
FAMILY_DETAIL = (
    ROOT / "connectors" / "mpsv" / "fixtures" / "family-2027.html"
).read_text(encoding="utf-8")
SOCIAL_DETAIL = (
    ROOT / "connectors" / "mpsv" / "fixtures" / "social-national-2026.html"
).read_text(encoding="utf-8")


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class MpsvAdapterTest(unittest.IsolatedAsyncioTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path.endswith(
            "dotace-na-podporu-rodiny-pro-nestatni-neziskove-organizace-v-dotacnim-rizeni-rodina"
        ):
            return httpx.Response(
                200,
                text=FAMILY_INDEX,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path.endswith("financni-prostredky-pro-rok-2026"):
            return httpx.Response(
                200,
                text=SOCIAL_INDEX,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path.endswith("dotacni-rizeni-pro-rok-2027") or path.endswith(
            "dotacni-rizeni-pro-rok-2026"
        ):
            return httpx.Response(
                200,
                text=FAMILY_DETAIL,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if "vyhlaseni-dotacniho-rizeni-v-oblasti-poskytovani-socialnich-sluzeb" in path:
            return httpx.Response(
                200,
                text=SOCIAL_DETAIL,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if "vyhlaseni-mimoradneho-dotacniho-rizeni-pro-socialni-sluzby" in path:
            return httpx.Response(
                200,
                text=SOCIAL_DETAIL,
                headers={"content-type": "text/html; charset=UTF-8"},
                request=request,
            )
        if path.startswith("/documents/"):
            mime = (
                "application/pdf"
                if path.endswith(".pdf")
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            return httpx.Response(
                200,
                content=b"fixture",
                headers={"content-type": mime},
                request=request,
            )
        return httpx.Response(404, request=request)

    async def context(self, tmp):
        client = GuardedHttpClient(
            allowed_hosts={"mpsv.gov.cz", "www.mpsv.gov.cz"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(self.handler),
        )
        return client, AdapterContext(
            run_id="mpsv-test",
            http=client,
            logger=None,
            budget=None,
            snapshots=LocalRawSnapshotStore(tmp),
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )

    async def test_discovery_combines_family_and_social_programmes(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                page = await MpsvAdapter().discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(page.total_hint, 4)
        ids = {item.external_id for item in page.items}
        self.assertIn("MPSV-RODINA-2026", ids)
        self.assertIn("MPSV-RODINA-2027", ids)
        self.assertTrue(any(i.startswith("MPSV-SOC-2026-") for i in ids))

    async def test_family_detail_extracts_decision_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = MpsvAdapter()
                page = await adapter.discover(ctx, None)
                item = next(
                    i for i in page.items
                    if i.external_id == "MPSV-RODINA-2027"
                )
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "CLOSED")
        self.assertEqual(record.raw_fields["programme"], "Rodina")
        self.assertEqual(record.raw_fields["year"], 2027)
        self.assertIn("nestátních neziskových", record.raw_fields["supportedActivitiesText"])
        self.assertIn("spolky", record.raw_fields["eligibleApplicantsText"])
        self.assertEqual(record.raw_fields["grantAmountMaxCzk"], 3_000_000)
        self.assertTrue(record.raw_fields["submissionOpenAt"])
        self.assertTrue(record.raw_fields["submissionCloseAt"])
        self.assertTrue(
            record.raw_fields["submissionCloseAt"].startswith("2026-09-16")
        )
        self.assertEqual(
            {artifact.role for artifact in record.artifacts},
            {"GUIDELINES", "ANNEX"},
        )
        self.assertTrue(record.snapshot_ids)

    async def test_social_detail_extracts_call_document_and_applicants(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = MpsvAdapter()
                page = await adapter.discover(ctx, None)
                item = next(
                    i for i in page.items
                    if i.external_id.startswith("MPSV-SOC-2026-")
                )
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertIsNotNone(record)
        self.assertEqual(record.native_status, "OPEN")
        self.assertIn(
            "sociální služby",
            record.raw_fields["supportedActivitiesText"],
        )
        self.assertIn(
            "registrované",
            record.raw_fields["supportedActivitiesText"],
        )
        self.assertIn(
            "Právnické a fyzické osoby",
            record.raw_fields["eligibleApplicantsText"],
        )
        roles = {artifact.role for artifact in record.artifacts}
        self.assertEqual(
            roles,
            {"CALL_DOCUMENT", "GUIDELINES", "APPLICATION_FORM"},
        )

    async def test_artifact_is_snapshotted(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ctx = await self.context(tmp)
            try:
                adapter = MpsvAdapter()
                page = await adapter.discover(ctx, None)
                item = next(
                    i for i in page.items
                    if i.external_id.startswith("MPSV-SOC-2026-")
                )
                record = (await adapter.fetch_record(ctx, item)).record
                artifact = next(
                    a for a in record.artifacts if a.role == "CALL_DOCUMENT"
                )
                result = await adapter.fetch_artifact(ctx, artifact)
            finally:
                await client.aclose()

        self.assertTrue(result.snapshot_id)
        self.assertGreater(result.size_bytes or 0, 0)


if __name__ == "__main__":
    unittest.main()
