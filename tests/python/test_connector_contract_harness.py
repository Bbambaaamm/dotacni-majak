import unittest
from datetime import timezone
from urllib.parse import urlsplit

from dotacni_majak_source_sdk import (
    ArtifactFetchResult,
    AuthorityLevel,
    DiscoveryItem,
    DiscoveryPage,
    FetchState,
    HealthReport,
    HealthStatus,
    NativeRecord,
    RecordFetchResult,
    RetrievalMode,
    SourceAdapter,
    SourceCheckpoint,
    SourceDescriptor,
)
from dotacni_majak_source_sdk.testing import (
    FixtureHttpClient,
    FixtureSnapshotStore,
    assert_descriptor_contract,
    exercise_adapter_contract,
    make_fixture_context,
)


class FakeAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="FAKE",
        name="Fake official source",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://example.com/",
        retrieval_modes=[RetrievalMode.HTML],
        allowed_hosts=["example.com"],
        adapter_version="1.0.0",
    )

    async def healthcheck(self, ctx):
        response = await ctx.http.get("https://example.com/list")
        return HealthReport(
            status=(
                HealthStatus.HEALTHY
                if response.status_code == 200
                else HealthStatus.DEGRADED
            ),
            checked_at=ctx.now,
        )

    async def discover(self, ctx, checkpoint):
        del checkpoint
        response = await ctx.http.get("https://example.com/list")
        snapshot = ctx.snapshots.put(
            source_code=self.descriptor.code,
            source_url="https://example.com/list",
            content=response.content,
            mime_type="text/html",
            retrieved_at=ctx.now,
        )
        return DiscoveryPage(
            items=[
                DiscoveryItem(
                    external_id="call-1",
                    detail_url="https://example.com/call-1",
                    metadata={"listing_snapshot_id": snapshot.snapshot_id},
                )
            ],
            is_complete=True,
            total_hint=1,
        )

    async def fetch_record(self, ctx, item, validators=None):
        del validators
        response = await ctx.http.get(str(item.detail_url))
        snapshot = ctx.snapshots.put(
            source_code=self.descriptor.code,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type="text/html",
            retrieved_at=ctx.now,
        )
        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title="Fixture call",
                native_status="OPEN",
                snapshot_ids=[snapshot.snapshot_id],
            ),
            http_status=response.status_code,
        )

    async def fetch_artifact(self, ctx, artifact, validators=None):
        del ctx, artifact, validators
        return ArtifactFetchResult(state=FetchState.GONE)


class ConnectorContractHarnessTest(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_http_and_snapshot_store_exercise_contract(self):
        http = FixtureHttpClient()
        http.add(
            "GET",
            "https://example.com/list",
            content="<html>list</html>",
            headers={"content-type": "text/html"},
        )
        http.add(
            "GET",
            "https://example.com/call-1",
            content="<html>detail</html>",
            headers={"content-type": "text/html"},
        )
        snapshots = FixtureSnapshotStore()
        ctx = make_fixture_context(http=http, snapshots=snapshots)

        report = await exercise_adapter_contract(FakeAdapter(), ctx)

        self.assertEqual(report.source_code, "FAKE")
        self.assertEqual(report.discovered, 1)
        self.assertEqual(report.first_record_state, FetchState.MODIFIED)
        self.assertGreaterEqual(report.snapshots_created, 2)
        self.assertEqual(
            [request.url for request in http.requests],
            [
                "https://example.com/list",
                "https://example.com/list",
                "https://example.com/call-1",
            ],
        )

    async def test_unexpected_fixture_request_fails_closed(self):
        http = FixtureHttpClient()
        with self.assertRaises(AssertionError):
            await http.get("https://example.com/unregistered")

    def test_descriptor_base_host_must_be_allowlisted(self):
        class BadAdapter(FakeAdapter):
            descriptor = SourceDescriptor(
                code="BAD",
                name="Bad",
                authority=AuthorityLevel.OFFICIAL,
                base_url="https://example.com/",
                retrieval_modes=[RetrievalMode.HTML],
                allowed_hosts=["other.example"],
                adapter_version="1",
            )

        with self.assertRaises(AssertionError):
            assert_descriptor_contract(BadAdapter())


if __name__ == "__main__":
    unittest.main()
