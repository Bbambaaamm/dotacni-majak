import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.outbox import OutboxEventType
from dotacni_majak_ingestion.outbox_worker import OutboxWorker, RetryPolicy
from dotacni_majak_ingestion.sqlite_outbox import SqliteOutboxRepository


T0 = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


class OutboxWorkerTest(unittest.IsolatedAsyncioTestCase):
    async def test_successful_handler_marks_event_delivered(self):
        connection = migrated_connection()
        repo = SqliteOutboxRepository(connection)
        event = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
            now=T0,
        )
        seen = []

        async def handler(current):
            seen.append((current.id, current.dedupe_key))

        worker = OutboxWorker(
            repository=repo,
            handlers={OutboxEventType.SEARCH_REINDEX_REQUIRED: handler},
            worker_id="worker-a",
            clock=lambda: T0,
        )
        result = await worker.run_once()

        self.assertEqual(result.status, "DELIVERED")
        self.assertEqual(seen, [(event.id, "search:v1")])
        self.assertEqual(repo.get(event.id).status.value, "DELIVERED")

    async def test_failing_handler_retries_then_dead_letters(self):
        connection = migrated_connection()
        repo = SqliteOutboxRepository(connection)
        event = repo.enqueue(
            event_type=OutboxEventType.VECTOR_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={},
            dedupe_key="vector:v1",
            now=T0,
        )
        clock_values = iter([
            T0, T0,
            T0 + timedelta(seconds=10), T0 + timedelta(seconds=10),
        ])

        async def failing(_):
            raise RuntimeError("vector backend down")

        worker = OutboxWorker(
            repository=repo,
            handlers={OutboxEventType.VECTOR_REINDEX_REQUIRED: failing},
            worker_id="worker-a",
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=10,
                max_delay_seconds=10,
            ),
            clock=lambda: next(clock_values),
        )

        first = await worker.run_once()
        self.assertEqual(first.status, "RETRY_SCHEDULED")

        second = await worker.run_once()
        self.assertEqual(second.status, "DEAD_LETTER")
        self.assertIsNotNone(repo.get(event.id).dead_lettered_at)

    async def test_missing_handler_is_safe_failure_not_lost_event(self):
        connection = migrated_connection()
        repo = SqliteOutboxRepository(connection)
        event = repo.enqueue(
            event_type=OutboxEventType.WATCH_REEVALUATION_REQUIRED,
            aggregate_type="Project",
            aggregate_id="p1",
            payload={},
            dedupe_key="watch:p1",
            now=T0,
        )
        worker = OutboxWorker(
            repository=repo,
            handlers={},
            worker_id="worker-a",
            retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=5),
            clock=lambda: T0,
        )

        result = await worker.run_once()

        self.assertEqual(result.status, "RETRY_SCHEDULED")
        persisted = repo.get(event.id)
        self.assertEqual(persisted.status.value, "FAILED")
        self.assertIn("no handler registered", persisted.last_error or "")


if __name__ == "__main__":
    unittest.main()
