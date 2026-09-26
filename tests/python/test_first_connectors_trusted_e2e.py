import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "nsa" / "src"))
sys.path.insert(0, str(ROOT / "connectors" / "eu-funding" / "src"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_eu_funding import EuFundingTendersAdapter
from dotacni_majak_ingestion.normalization import (
    EuFundingGrantNormalizer,
    NsaGrantNormalizer,
)
from dotacni_majak_ingestion.outbox import OutboxEventType
from dotacni_majak_ingestion.outbox_worker import OutboxWorker
from dotacni_majak_ingestion.search_projection import SqliteSearchProjection
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_ingestion.sqlite_outbox import SqliteOutboxRepository
from dotacni_majak_ingestion.trusted_ingest import TrustedGrantIngestor
from dotacni_majak_nsa import NsaAdapter
from dotacni_majak_source_sdk import AdapterContext, GuardedHttpClient


NSA_LISTING = (
    ROOT / "connectors" / "nsa" / "fixtures" / "investment-listing.html"
).read_text(encoding="utf-8")
NSA_DETAIL = (
    ROOT / "connectors" / "nsa" / "fixtures" / "call-16-2026.html"
).read_text(encoding="utf-8")
EU_FIXTURE = json.loads(
    (
        ROOT
        / "connectors"
        / "eu-funding"
        / "fixtures"
        / "search-page-1.json"
    ).read_text(encoding="utf-8")
)


async def public_resolver(host: str, port: int) -> list[str]:
    del host, port
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


async def drain_projection_outbox(
    connection: sqlite3.Connection,
    *,
    count: int = 2,
) -> None:
    repository = SqliteOutboxRepository(connection)
    projection = SqliteSearchProjection(connection)

    def change_detection_placeholder(event):
        # #572 proves the canonical->search dependency. Change classification
        # has its own tested domain package and is not required to mutate the
        # search projection here.
        if event.event_type is not OutboxEventType.CHANGE_DETECTION_REQUIRED:
            raise ValueError("unexpected placeholder event")

    worker = OutboxWorker(
        repository=repository,
        handlers={
            OutboxEventType.SEARCH_REINDEX_REQUIRED: projection.handle_outbox,
            OutboxEventType.CHANGE_DETECTION_REQUIRED: change_detection_placeholder,
        },
        worker_id="e2e-worker",
        clock=lambda: datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc),
    )
    delivered = []
    for _ in range(count):
        result = await worker.run_once()
        delivered.append(result.status)
    if delivered != ["DELIVERED"] * count:
        raise AssertionError(delivered)


class FirstConnectorsTrustedE2ETest(unittest.IsolatedAsyncioTestCase):
    async def test_nsa_html_fixture_raw_to_canonical_evidence_and_search(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path in {
                "/dotace-investicni/",
                "/dotace-neinvesticni/",
                "/dotace-neinvesticni-parasport/",
            }:
                return httpx.Response(
                    200,
                    text=NSA_LISTING,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            if path.startswith("/dotace/vyzva-16-2026"):
                return httpx.Response(
                    200,
                    text=NSA_DETAIL,
                    headers={"content-type": "text/html; charset=UTF-8"},
                    request=request,
                )
            return httpx.Response(404, request=request)

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawSnapshotStore(tmp)
            client = GuardedHttpClient(
                allowed_hosts={"nsa.gov.cz", "www.nsa.gov.cz"},
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="e2e-nsa",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=store,
                    now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
                )
                adapter = NsaAdapter()
                item = (await adapter.discover(ctx, None)).items[0]
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

            self.assertIsNotNone(record)
            grant = NsaGrantNormalizer().normalize(item, record, ctx.now)
            raw = store.load_by_sha256(
                source_code="NSA",
                sha256=grant.content_hash,
            )

            connection = migrated_connection()
            ingested = TrustedGrantIngestor(connection).ingest(
                grant,
                record_snapshot=raw,
                now=ctx.now,
            )
            await drain_projection_outbox(connection)

        self.assertEqual(grant.source_external_id, "16/2026")
        self.assertEqual(grant.status, "CLOSED")
        self.assertTrue(
            ingested.document_version.source_url.startswith(
                "https://nsa.gov.cz/"
            )
        )
        evidence_count = connection.execute(
            "SELECT COUNT(*) FROM field_evidence WHERE entity_id=?",
            (ingested.publication.grant_call_version_id,),
        ).fetchone()[0]
        self.assertGreaterEqual(evidence_count, 3)

        fts = connection.execute(
            """SELECT grant_call_version_id FROM grant_search_fts
               WHERE grant_search_fts MATCH 'sport*'"""
        ).fetchall()
        self.assertTrue(fts)

        # Historical CLOSED fixture must not masquerade as an active result.
        active = connection.execute(
            """SELECT d.grant_call_version_id
               FROM grant_search_fts
               JOIN grant_search_documents d USING(grant_call_version_id)
               WHERE grant_search_fts MATCH 'sport*'
                 AND d.status IN ('OPEN','PLANNED','ANNOUNCED')"""
        ).fetchall()
        self.assertEqual(active, [])

    async def test_eu_funding_api_fixture_raw_to_open_searchable_result(self):
        first_only = {**EU_FIXTURE, "results": [EU_FIXTURE["results"][0]]}

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            return httpx.Response(
                200,
                json=first_only,
                headers={"content-type": "application/json"},
                request=request,
            )

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawSnapshotStore(tmp)
            client = GuardedHttpClient(
                allowed_hosts={"api.tech.ec.europa.eu", "ec.europa.eu"},
                allowed_post_paths={"/search-api/prod/rest/search"},
                resolver=public_resolver,
                sleeper=no_sleep,
                transport=httpx.MockTransport(handler),
            )
            try:
                ctx = AdapterContext(
                    run_id="e2e-eu-ft",
                    http=client,
                    logger=None,
                    budget=None,
                    snapshots=store,
                    now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
                )
                adapter = EuFundingTendersAdapter(page_size=1)
                item = (await adapter.discover(ctx, None)).items[0]
                record = (await adapter.fetch_record(ctx, item)).record
            finally:
                await client.aclose()

            self.assertIsNotNone(record)
            grant = EuFundingGrantNormalizer().normalize(item, record, ctx.now)
            raw = store.load_by_sha256(
                source_code="EU_FT",
                sha256=grant.content_hash,
            )

            connection = migrated_connection()
            ingested = TrustedGrantIngestor(connection).ingest(
                grant,
                record_snapshot=raw,
                now=ctx.now,
            )
            await drain_projection_outbox(connection)

        self.assertEqual(
            grant.source_external_id,
            "ISF-2026-TF2-AG-CORRUPT",
        )
        self.assertEqual(grant.status, "OPEN")
        self.assertTrue(
            ingested.document_version.source_url.startswith(
                "https://api.tech.ec.europa.eu/"
            )
        )
        active = connection.execute(
            """SELECT d.grant_call_version_id,d.status
               FROM grant_search_fts
               JOIN grant_search_documents d USING(grant_call_version_id)
               WHERE grant_search_fts MATCH 'corrupt*'
                 AND d.status IN ('OPEN','PLANNED','ANNOUNCED')"""
        ).fetchall()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0][1], "OPEN")

        staging = connection.execute(
            """SELECT state FROM canonical_staging_items
               WHERE published_entity_id=?""",
            (ingested.publication.grant_call_version_id,),
        ).fetchone()
        self.assertEqual(staging[0], "PUBLISHED")
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE status='DELIVERED'"
            ).fetchone()[0],
            2,
        )


if __name__ == "__main__":
    unittest.main()
