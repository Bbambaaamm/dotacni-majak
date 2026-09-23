import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.data_quality import (
    QualityGateStatus,
    SourceRunObservation,
    SourceRunQualityGate,
)
from dotacni_majak_ingestion.outbox import (
    InMemoryOutboxRepository,
    OutboxEventType,
    OutboxStatus,
)
from dotacni_majak_ingestion.quarantine import (
    InMemoryQuarantineRepository,
    QuarantineReason,
)


class QualityGateTest(unittest.TestCase):
    def test_zero_records_against_stable_baseline_blocks_destructive_changes(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=0,
                baseline_samples=8,
                baseline_median_records=120,
                http_requests=20,
                http_errors=0,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)
        self.assertIn(
            "RECORD_COUNT_COLLAPSE",
            {violation.code for violation in decision.violations},
        )

    def test_healthy_run_allows_destructive_changes(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=108,
                baseline_samples=10,
                baseline_median_records=120,
                http_requests=20,
                http_errors=1,
                parse_attempts=108,
                parse_failures=2,
                validation_attempts=106,
                validation_failures=1,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)

    def test_first_empty_run_without_baseline_is_not_assumed_broken(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(records_found=0)
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)

    def test_structure_change_degrades_source(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=50,
                unexpected_structure_change=True,
            )
        )
        self.assertTrue(decision.is_degraded)
        self.assertFalse(decision.destructive_changes_allowed)


class OutboxTest(unittest.TestCase):
    def test_enqueue_is_idempotent_by_dedupe_key(self):
        repo = InMemoryOutboxRepository()
        first = repo.enqueue(
            event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v2",
            payload={"from": "v1", "to": "v2"},
            dedupe_key="change:v1:v2",
        )
        second = repo.enqueue(
            event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v2",
            payload={"from": "v1", "to": "v2"},
            dedupe_key="change:v1:v2",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(repo.pending()), 1)

    def test_failed_event_can_be_claimed_again(self):
        repo = InMemoryOutboxRepository()
        event = repo.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v2",
            payload={},
            dedupe_key="search:v2",
        )
        claimed = repo.claim(event.id)
        self.assertEqual(claimed.attempts, 1)
        failed = repo.mark_failed(event.id, RuntimeError("boom"))
        self.assertEqual(failed.status, OutboxStatus.FAILED)
        claimed_again = repo.claim(event.id)
        self.assertEqual(claimed_again.attempts, 2)
        delivered = repo.mark_delivered(event.id)
        self.assertEqual(delivered.status, OutboxStatus.DELIVERED)
        self.assertEqual(repo.pending(), [])


class QuarantineTest(unittest.TestCase):
    def test_item_stays_open_until_explicit_resolution(self):
        repo = InMemoryQuarantineRepository()
        item = repo.add(
            source_code="NSA",
            external_id="call-1",
            reason=QuarantineReason.VALIDATION_FAILED,
            details="invalid deadline",
        )
        self.assertEqual([item.id], [x.id for x in repo.unresolved()])
        resolved = repo.resolve(item.id, note="fixed by parser v2")
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(repo.unresolved(), [])


if __name__ == "__main__":
    unittest.main()
