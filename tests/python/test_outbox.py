import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.outbox import (
    InMemoryOutboxRepository,
    OutboxEventType,
    OutboxStatus,
)


class OutboxTest(unittest.TestCase):
    def test_dedupe_key_is_idempotent(self):
        repo = InMemoryOutboxRepository()
        first = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
        )
        second = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(repo.pending()), 1)

    def test_failed_event_remains_retryable(self):
        repo = InMemoryOutboxRepository()
        event = repo.enqueue(
            event_type=OutboxEventType.NOTIFICATION_REQUIRED,
            aggregate_type="ChangeEvent",
            aggregate_id="c1",
            payload={},
            dedupe_key="notify:c1",
        )
        claimed = repo.claim(event.id)
        self.assertEqual(claimed.status, OutboxStatus.PROCESSING)
        self.assertEqual(claimed.attempts, 1)

        failed = repo.mark_failed(event.id, RuntimeError("provider unavailable"))
        self.assertEqual(failed.status, OutboxStatus.FAILED)
        self.assertEqual(len(repo.pending()), 1)

        claimed_again = repo.claim(event.id)
        self.assertEqual(claimed_again.attempts, 2)

    def test_delivered_event_is_not_pending(self):
        repo = InMemoryOutboxRepository()
        event = repo.enqueue(
            event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v2",
            payload={},
            dedupe_key="change:v2",
        )
        repo.mark_delivered(event.id)
        self.assertEqual(repo.pending(), [])


if __name__ == "__main__":
    unittest.main()
