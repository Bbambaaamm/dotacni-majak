import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.orchestrator import (
    IngestionOrchestrator,
    IngestionRunStatus,
    PassthroughRecordPipeline,
)
from dotacni_majak_ingestion.sqlite_repository import SqliteIngestionRepository
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
    RetrievalMode,
    SourceAdapter,
    SourceCheckpoint,
    SourceDescriptor,
)


T0 = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


class OnePageAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="TEST",
        name="Test",
        authority="OFFICIAL",
        base_url="https://example.com/",
        retrieval_modes=[RetrievalMode.API],
        allowed_hosts=["example.com"],
        adapter_version="1",
    )

    async def healthcheck(self, ctx):
        return HealthReport(status=HealthStatus.HEALTHY, checked_at=ctx.now)

    async def discover(self, ctx, checkpoint):
        del ctx, checkpoint
        return DiscoveryPage(
            items=[
                DiscoveryItem(
                    external_id="x",
                    detail_url="https://example.com/x",
                )
            ],
            next_checkpoint=SourceCheckpoint(cursor="done"),
            is_complete=True,
        )

    async def fetch_record(self, ctx, item, validators=None):
        del ctx, validators
        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code="TEST",
                external_id=item.external_id,
                detail_url=item.detail_url,
                snapshot_ids=["TEST:" + "a" * 64],
            ),
        )

    async def fetch_artifact(self, ctx, artifact, validators=None):
        del ctx, artifact, validators
        return ArtifactFetchResult(state=FetchState.GONE)


class PersistentOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_audits_run_and_persists_checkpoint(self):
        connection = migrated_connection()
        now_values = iter([
            T0,
            T0 + timedelta(seconds=5),
            T0 + timedelta(seconds=6),
            T0 + timedelta(seconds=7),
        ])
        repo = SqliteIngestionRepository(
            connection,
            run_id="run-1",
            clock=lambda: T0,
        )
        orchestrator = IngestionOrchestrator(
            repository=repo,
            pipeline=PassthroughRecordPipeline(),
            lease_seconds=60,
            clock=lambda: next(now_values),
        )
        ctx = AdapterContext(
            run_id="run-1",
            http=None,
            logger=None,
            budget=None,
            snapshots=None,
            now=T0,
        )

        result = await orchestrator.run(OnePageAdapter(), ctx)

        self.assertEqual(result.status, IngestionRunStatus.COMPLETED)
        self.assertEqual(repo.get_checkpoint("TEST").cursor, "done")
        row = connection.execute(
            "SELECT status, processed, pages FROM ingestion_runs WHERE id = 'run-1'"
        ).fetchone()
        self.assertEqual(row, ("COMPLETED", 1, 1))
        self.assertIsNone(
            connection.execute(
                "SELECT source_code FROM ingestion_locks WHERE source_code='TEST'"
            ).fetchone()
        )

    async def test_existing_live_lock_returns_locked_without_discovery(self):
        connection = migrated_connection()
        holder = SqliteIngestionRepository(
            connection,
            run_id="holder",
            clock=lambda: T0,
        )
        holder.acquire_lock("TEST", "holder", now=T0, lease_seconds=120)

        contender = SqliteIngestionRepository(
            connection,
            run_id="run-2",
            clock=lambda: T0 + timedelta(seconds=10),
        )
        orchestrator = IngestionOrchestrator(
            repository=contender,
            pipeline=PassthroughRecordPipeline(),
            lease_seconds=60,
            clock=lambda: T0 + timedelta(seconds=10),
        )
        ctx = AdapterContext(
            run_id="run-2",
            http=None,
            logger=None,
            budget=None,
            snapshots=None,
            now=T0 + timedelta(seconds=10),
        )

        result = await orchestrator.run(OnePageAdapter(), ctx)

        self.assertEqual(result.status, IngestionRunStatus.LOCKED)
        audit = connection.execute(
            "SELECT status, last_error FROM ingestion_runs WHERE id='run-2'"
        ).fetchone()
        self.assertEqual(audit[0], "LOCKED")
        self.assertIn("lock", audit[1])


if __name__ == "__main__":
    unittest.main()
