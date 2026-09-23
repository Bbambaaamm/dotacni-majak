import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "jdp" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_jdp import JdpAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


FIXTURE = ROOT / "connectors" / "jdp" / "fixtures" / "open-page.json"
STATUS_FIXTURE = ROOT / "connectors" / "jdp" / "fixtures" / "status-list.json"


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class JdpAdapterTest(unittest.IsolatedAsyncioTestCase):
    def payload(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    async def test_discovery_uses_observed_public_request_contract(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json=self.payload(),
                headers={"content-type": "application/json; charset=utf-8"},
                request=request,
            )

        with tempfile.TemporaryDirectory() as tmp:
            client = GuardedHttpClient(
                allowed_hosts={"jdp2.mf.gov.cz"},
                allowed_post_paths={
                    "/jdp_api/api/nxwebedppublicdashboard/kodyvyzva"
                },
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="jdp-test",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=LocalRawSnapshotStore(tmp),
                    now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
                )
                page = await JdpAdapter(page_size=2).discover(ctx, None)
            finally:
                await client.aclose()

        self.assertEqual(seen["method"], "POST")
        self.assertEqual(
            seen["path"],
            "/jdp_api/api/nxwebedppublicdashboard/kodyvyzva",
        )
        self.assertEqual(seen["payload"]["fkName"], "stavVyzvaLongWeb")
        self.assertEqual(seen["payload"]["fkValue"], "Otevřená")
        self.assertEqual(
            seen["payload"]["filterTree"]["filter"],
            {
                "operator": "eq",
                "propName": "stavVyzvaLong",
                "value": "Běžící",
            },
        )
        self.assertEqual(seen["payload"]["pageIndex"], 0)
        self.assertEqual(seen["payload"]["pageSize"], 2)
        self.assertEqual(len(page.items), 2)
        self.assertEqual(page.total_hint, 3)
        self.assertFalse(page.is_complete)
        self.assertEqual(page.next_checkpoint.cursor, "1")
        self.assertTrue(page.items[0].metadata["discovery_snapshot_id"])

    async def test_fetch_record_preserves_source_values_and_normalizes_money(self):
        payload = self.payload()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=payload,
                headers={"content-type": "application/json"},
                request=request,
            )

        with tempfile.TemporaryDirectory() as tmp:
            client = GuardedHttpClient(
                allowed_hosts={"jdp2.mf.gov.cz"},
                allowed_post_paths={
                    "/jdp_api/api/nxwebedppublicdashboard/kodyvyzva"
                },
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="jdp-record",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=LocalRawSnapshotStore(tmp),
                    now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
                )
                adapter = JdpAdapter(page_size=2)
                item = (await adapter.discover(ctx, None)).items[0]
                result = await adapter.fetch_record(ctx, item)
            finally:
                await client.aclose()

        record = result.record
        self.assertIsNotNone(record)
        self.assertEqual(record.external_id, payload["result"]["items"][0]["id"])
        self.assertEqual(record.native_status, "Otevřená")
        self.assertEqual(record.raw_fields["normalizedStatus"], "OPEN")
        self.assertEqual(record.raw_fields["grantAmountMinMinor"], 10_000_000)
        self.assertEqual(record.raw_fields["grantAmountMaxMinor"], 500_000_000)
        self.assertEqual(record.raw_fields["allocationMinor"], 10_000_000_000)
        self.assertEqual(record.raw_fields["supportRateMaxSource"], 80)
        self.assertTrue(record.snapshot_ids)
        self.assertEqual(
            str(record.detail_url),
            "https://jdp2.mf.gov.cz/public/detail/test-2026-a",
        )

    async def test_external_public_link_is_not_promoted_to_source_detail_url(self):
        payload = self.payload()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload, request=request)

        with tempfile.TemporaryDirectory() as tmp:
            client = GuardedHttpClient(
                allowed_hosts={"jdp2.mf.gov.cz"},
                allowed_post_paths={
                    "/jdp_api/api/nxwebedppublicdashboard/kodyvyzva"
                },
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="jdp-external-link",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=LocalRawSnapshotStore(tmp),
                    now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
                )
                adapter = JdpAdapter(page_size=2)
                item = (await adapter.discover(ctx, None)).items[1]
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

        self.assertEqual(str(record.detail_url), "https://jdp2.mf.gov.cz/")
        self.assertEqual(
            record.raw_fields["publicLink"],
            "https://external.example.invalid/application",
        )

    async def test_healthcheck_uses_public_status_endpoint(self):
        status_payload = json.loads(
            STATUS_FIXTURE.read_text(encoding="utf-8")
        )

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/jdp_api/api/NxWebEDPPublicDashboard/KodyVyzvaStav",
            )
            return httpx.Response(200, json=status_payload, request=request)

        client = GuardedHttpClient(
            allowed_hosts={"jdp2.mf.gov.cz"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(handler),
        )
        try:
            ctx = AdapterContext(
                run_id="jdp-health",
                http=client,
                logger=None,
                budget=None,
                snapshots=None,
                now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
            )
            health = await JdpAdapter().healthcheck(ctx)
        finally:
            await client.aclose()

        self.assertEqual(health.status.value, "HEALTHY")


if __name__ == "__main__":
    unittest.main()
