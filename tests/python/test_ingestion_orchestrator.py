import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.orchestrator import (
    InMemoryIngestionRepository,
    IngestionOrchestrator,
    IngestionRunStatus,
    PassthroughRecordPipeline,
)
from dotacni_majak_ingestion.state import IngestionState

from dotacni_majak_source_sdk import (
    AdapterContext,
    ArtifactFetchResult,
    DiscoveryItem,
    DiscoveryPage,
    FetchState,
    HealthReport,
    HealthStatus,
    NativeRecord,
    RecordFetchResult,
    RemoteArtifactRef,
    RetrievalMode,
    SourceAdapter,
    SourceCheckpoint,
    SourceDescriptor,
)


class FakeAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="TEST",
        name="Test Source",
        authority="OFFICIAL",
        base_url="https://example.com",
        retrieval_modes=[RetrievalMode.API],
        allowed_hosts=["example.com"],
        adapter_version="1",
    )

    def __init__(self, items, unavailable=False):
        self.items = items
        self.unavailable = unavailable
        self.discover_calls = 0
        self.fetch_calls = []

    async def healthcheck(self, ctx):
        return HealthReport(
            status=(
                HealthStatus.UNAVAILABLE
                if self.unavailable
                else HealthStatus.HEALTHY
            ),
            checked_at=ctx.now,
        )

    async def discover(self, ctx, checkpoint):
        self.discover_calls += 1
        return DiscoveryPage(
            items=[
                DiscoveryItem(
                    external_id=item,
                    detail_url=f"https://example.com/{item}",
                )
                for item in self.items
            ],
            next_checkpoint=SourceCheckpoint(cursor="page-1-done"),
            is_complete=True,
        )

    async def fetch_record(self, ctx, item, validators=None):
        self.fetch_calls.append(item.external_id)
        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code="TEST",
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=item.external_id,
                snapshot_ids=[f"raw:{item.external_id}"],
            ),
        )

    async def fetch_artifact(self, ctx, artifact, validators=None):
        return ArtifactFetchResult(
            state=FetchState.MODIFIED,
            snapshot_id=f"raw-artifact:{artifact.external_id}",
        )


class FailOncePipeline(PassthroughRecordPipeline):
    def __init__(self):
        self.failed = False

    async def validate(self, normalized):
        if normalized.external_id == "b" and not self.failed:
            self.failed = True
            raise ValueError("simulated validation failure")
        return normalized


def context():
    return AdapterContext(
        run_id="run-1",
        http=None,
        logger=None,
        budget=None,
        now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
    )


class IngestionOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_commits_checkpoint_only_after_page_success(self):
        repo = InMemoryIngestionRepository()
        adapter = FakeAdapter(["a", "b"])
        pipeline = FailOncePipeline()
        orchestrator = IngestionOrchestrator(
            repository=repo,
            pipeline=pipeline,
        )

        first = await orchestrator.run(adapter, context())
        self.assertEqual(first.status, IngestionRunStatus.PARTIAL_FAILED)
        self.assertIsNone(repo.get_checkpoint("TEST"))
        self.assertEqual(
            repo.items[("TEST", "a")].state,
            IngestionState.COMPLETED,
        )
        self.assertEqual(
            repo.items[("TEST", "b")].state,
            IngestionState.RETRYABLE_FAILED,
        )

        second = await orchestrator.run(adapter, context())
        self.assertEqual(second.status, IngestionRunStatus.COMPLETED)
        self.assertEqual(repo.get_checkpoint("TEST").cursor, "page-1-done")
        self.assertEqual(adapter.fetch_calls.count("a"), 1)
        self.assertEqual(adapter.fetch_calls.count("b"), 2)

    async def test_unavailable_source_does_not_discover(self):
        repo = InMemoryIngestionRepository()
        adapter = FakeAdapter(["a"], unavailable=True)
        orchestrator = IngestionOrchestrator(
            repository=repo,
            pipeline=PassthroughRecordPipeline(),
        )

        result = await orchestrator.run(adapter, context())
        self.assertEqual(result.status, IngestionRunStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(adapter.discover_calls, 0)

    async def test_completed_items_are_idempotently_skipped(self):
        repo = InMemoryIngestionRepository()
        adapter = FakeAdapter(["a"])
        orchestrator = IngestionOrchestrator(
            repository=repo,
            pipeline=PassthroughRecordPipeline(),
        )

        first = await orchestrator.run(adapter, context())
        second = await orchestrator.run(adapter, context())

        self.assertEqual(first.processed, 1)
        self.assertEqual(second.skipped, 1)
        self.assertEqual(adapter.fetch_calls.count("a"), 1)


if __name__ == "__main__":
    unittest.main()
