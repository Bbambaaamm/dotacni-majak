import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.outbox import OutboxEventType, OutboxStatus
from dotacni_majak_ingestion.sqlite_outbox import (
    OutboxLeaseError,
    SqliteOutboxRepository,
)


T0 = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


class SqliteOutboxRepositoryTest(unittest.TestCase):
    def test_enqueue_is_idempotent_by_dedupe_key(self):
        connection = migrated_connection()
        repo = SqliteOutboxRepository(connection)
        first = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
            now=T0,
        )
        second = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
            now=T0,
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0],
            1,
        )

    def test_enqueue_can_share_caller_transaction_with_canonical_write(self):
        connection = migrated_connection()
        connection.isolation_level = None
        repo = SqliteOutboxRepository(connection)

        connection.execute("BEGIN")
        connection.execute(
            "INSERT INTO providers(id,name,provider_type) VALUES ('p','Provider','NATIONAL')"
        )
        repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="Provider",
            aggregate_id="p",
            payload={"provider_id": "p"},
            dedupe_key="provider:p",
            now=T0,
            commit=False,
        )
        connection.execute("ROLLBACK")

        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM providers WHERE id='p'").fetchone()[0],
            0,
        )
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE dedupe_key='provider:p'"
            ).fetchone()[0],
            0,
        )

    def test_claim_lease_blocks_second_worker_until_expiry(self):
        connection = migrated_connection()
        repo = SqliteOutboxRepository(connection)
        event = repo.enqueue(
            event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type="GrantCall",
            aggregate_id="g1",
            payload={},
            dedupe_key="change:g1",
            now=T0,
        )

        first = repo.claim_next(
            worker_id="worker-a",
            now=T0,
            lease_seconds=60,
        )
        self.assertEqual(first.id, event.id)
        self.assertEqual(first.status, OutboxStatus.PROCESSING)
        self.assertEqual(first.attempts, 1)

        self.assertIsNone(
            repo.claim_next(
                worker_id="worker-b",
                now=T0 + timedelta(seconds=30),
                lease_seconds=60,
            )
        )

        reclaimed = repo.claim_next(
            worker_id="worker-b",
            now=T0 + timedelta(seconds=61),
            lease_seconds=60,
        )
        self.assertEqual(reclaimed.id, event.id)
        self.assertEqual(reclaimed.attempts, 2)
        self.assertEqual(reclaimed.lease_owner, "worker-b")

        with self.assertRaises(OutboxLeaseError):
            repo.mark_delivered(
                event.id,
                worker_id="worker-a",
                now=T0 + timedelta(seconds=62),
            )

    def test_failure_schedules_retry_then_dead_letters_at_max_attempts(self):
        connection = migrated_connection()
        repo = SqliteOutboxRepository(connection)
        event = repo.enqueue(
            event_type=OutboxEventType.NOTIFICATION_REQUIRED,
            aggregate_type="Watch",
            aggregate_id="w1",
            payload={},
            dedupe_key="notify:w1",
            now=T0,
        )

        first = repo.claim_next(worker_id="w", now=T0, lease_seconds=60)
        failed = repo.mark_failed(
            first.id,
            worker_id="w",
            error=RuntimeError("temporary"),
            now=T0,
            max_attempts=2,
            retry_after_seconds=30,
        )
        self.assertEqual(failed.status, OutboxStatus.FAILED)
        self.assertIsNone(failed.dead_lettered_at)
        self.assertIsNone(
            repo.claim_next(
                worker_id="w",
                now=T0 + timedelta(seconds=20),
                lease_seconds=60,
            )
        )

        second = repo.claim_next(
            worker_id="w",
            now=T0 + timedelta(seconds=30),
            lease_seconds=60,
        )
        self.assertEqual(second.attempts, 2)
        dead = repo.mark_failed(
            second.id,
            worker_id="w",
            error=RuntimeError("still failing"),
            now=T0 + timedelta(seconds=30),
            max_attempts=2,
            retry_after_seconds=60,
        )
        self.assertIsNotNone(dead.dead_lettered_at)
        self.assertIsNone(
            repo.claim_next(
                worker_id="other",
                now=T0 + timedelta(days=1),
                lease_seconds=60,
            )
        )
        self.assertEqual(repo.metrics(now=T0 + timedelta(days=1))["dead_letter"], 1)


if __name__ == "__main__":
    unittest.main()
