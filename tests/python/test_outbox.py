import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.outbox import (
    InMemoryOutboxRepository,
    OutboxEventType,
    OutboxStatus,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


class OutboxTest(unittest.TestCase):
    def test_dedupe_key_makes_enqueue_idempotent(self):
        repo = InMemoryOutboxRepository()
        a = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
            now=NOW,
        )
        b = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
            now=NOW,
        )
        self.assertEqual(a.id, b.id)
        self.assertEqual(len(repo.pending()), 1)

    def test_failed_event_remains_retryable(self):
        repo = InMemoryOutboxRepository()
        event = repo.enqueue(
            event_type=OutboxEventType.VECTOR_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={},
            dedupe_key="vector:v1",
            now=NOW,
        )
        claimed = repo.claim(event.id)
        self.assertEqual(claimed.status, OutboxStatus.PROCESSING)
        failed = repo.mark_failed(event.id, RuntimeError("down"))
        self.assertEqual(failed.status, OutboxStatus.FAILED)
        self.assertEqual(len(repo.pending()), 1)
        retry = repo.claim(event.id)
        self.assertEqual(retry.attempts, 2)

    def test_delivered_event_leaves_pending_set(self):
        repo = InMemoryOutboxRepository()
        event = repo.enqueue(
            event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type="GrantCall",
            aggregate_id="g1",
            payload={},
            dedupe_key="change:g1:v2",
            now=NOW,
        )
        repo.claim(event.id)
        delivered = repo.mark_delivered(event.id, now=NOW)
        self.assertEqual(delivered.status, OutboxStatus.DELIVERED)
        self.assertEqual(repo.pending(), [])


if __name__ == "__main__":
    unittest.main()
