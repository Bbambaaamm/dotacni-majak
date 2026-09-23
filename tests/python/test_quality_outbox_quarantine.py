import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion import (
    InMemoryOutboxRepository,
    InMemoryQuarantineRepository,
    OutboxEventType,
    QualityGateStatus,
    QuarantineReason,
    SourceRunObservation,
    SourceRunQualityGate,
)


class QualityOutboxQuarantineTest(unittest.TestCase):
    def test_zero_records_against_stable_baseline_is_degraded(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=0,
                baseline_samples=5,
                baseline_median_records=120,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)
        self.assertIn(
            "RECORD_COUNT_COLLAPSE",
            {violation.code for violation in decision.violations},
        )

    def test_healthy_source_allows_destructive_changes(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=118,
                baseline_samples=5,
                baseline_median_records=120,
                http_requests=100,
                http_errors=1,
                parse_attempts=118,
                parse_failures=1,
                validation_attempts=117,
                validation_failures=1,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)

    def test_structure_change_always_degrades(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=120,
                unexpected_structure_change=True,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)

    def test_outbox_deduplicates_and_tracks_retry(self):
        outbox = InMemoryOutboxRepository()
        kwargs = dict(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="version-1",
            payload={"version": 1},
            dedupe_key="grant-version-1-search",
        )
        first = outbox.enqueue(**kwargs)
        duplicate = outbox.enqueue(**kwargs)
        self.assertEqual(first.id, duplicate.id)

        claimed = outbox.claim(first.id)
        self.assertEqual(claimed.attempts, 1)

        failed = outbox.mark_failed(first.id, RuntimeError("temporary"))
        self.assertEqual(failed.status.value, "FAILED")
        self.assertEqual(len(outbox.pending()), 1)

        claimed_again = outbox.claim(first.id)
        self.assertEqual(claimed_again.attempts, 2)
        delivered = outbox.mark_delivered(first.id)
        self.assertEqual(delivered.status.value, "DELIVERED")
        self.assertEqual(outbox.pending(), [])

    def test_quarantine_is_resolvable_without_deleting_history(self):
        quarantine = InMemoryQuarantineRepository()
        item = quarantine.add(
            source_code="NSA",
            reason=QuarantineReason.VALIDATION_FAILED,
            external_id="call-1",
            details="missing title",
            payload_ref="raw:NSA:abc",
        )
        self.assertEqual(len(quarantine.unresolved(source_code="NSA")), 1)

        resolved = quarantine.resolve(item.id, note="parser fixed")
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(quarantine.unresolved(source_code="NSA"), [])


if __name__ == "__main__":
    unittest.main()
