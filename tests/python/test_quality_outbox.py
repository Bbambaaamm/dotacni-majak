import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion import (
    InMemoryOutboxRepository,
    InMemoryQuarantineRepository,
    OutboxEventType,
    OutboxStatus,
    QualityGateStatus,
    QuarantineReason,
    SourceRunObservation,
    SourceRunQualityGate,
)


class DataQualityGateTest(unittest.TestCase):
    def test_zero_records_against_stable_baseline_degrades(self):
        gate = SourceRunQualityGate()
        decision = gate.evaluate(
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

    def test_low_parse_success_degrades(self):
        gate = SourceRunQualityGate()
        decision = gate.evaluate(
            SourceRunObservation(
                records_found=100,
                baseline_samples=4,
                baseline_median_records=100,
                parse_attempts=100,
                parse_failures=30,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)

    def test_healthy_run_allows_destructive_changes(self):
        gate = SourceRunQualityGate()
        decision = gate.evaluate(
            SourceRunObservation(
                records_found=99,
                baseline_samples=5,
                baseline_median_records=100,
                http_requests=50,
                http_errors=1,
                parse_attempts=99,
                parse_failures=0,
                validation_attempts=99,
                validation_failures=1,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)

    def test_structure_change_degrades_even_with_same_record_count(self):
        gate = SourceRunQualityGate()
        decision = gate.evaluate(
            SourceRunObservation(
                records_found=100,
                baseline_samples=5,
                baseline_median_records=100,
                unexpected_structure_change=True,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)


class OutboxTest(unittest.TestCase):
    def test_enqueue_is_idempotent_by_dedupe_key(self):
        outbox = InMemoryOutboxRepository()
        first = outbox.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
        )
        second = outbox.enqueue(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="GrantCallVersion",
            aggregate_id="v1",
            payload={"version_id": "v1"},
            dedupe_key="search:v1",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(outbox.pending()), 1)

    def test_failed_event_can_be_retried_and_delivered(self):
        outbox = InMemoryOutboxRepository()
        event = outbox.enqueue(
            event_type=OutboxEventType.NOTIFICATION_REQUIRED,
            aggregate_type="Watch",
            aggregate_id="w1",
            payload={},
            dedupe_key="notify:w1:c1",
        )

        claimed = outbox.claim(event.id)
        self.assertEqual(claimed.attempts, 1)
        outbox.mark_failed(event.id, RuntimeError("temporary"))
        self.assertEqual(outbox.pending()[0].status, OutboxStatus.FAILED)

        claimed = outbox.claim(event.id)
        self.assertEqual(claimed.attempts, 2)
        delivered = outbox.mark_delivered(
            event.id,
            now=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )
        self.assertEqual(delivered.status, OutboxStatus.DELIVERED)
        self.assertEqual(outbox.pending(), [])


class QuarantineTest(unittest.TestCase):
    def test_invalid_payload_can_be_quarantined_without_publish(self):
        quarantine = InMemoryQuarantineRepository()
        item = quarantine.add(
            source_code="NSA",
            external_id="call-1",
            reason=QuarantineReason.VALIDATION_FAILED,
            details="support rate lacks required evidence",
            payload_ref="raw/NSA/ab/cd/hash.bin",
        )
        self.assertFalse(item.is_resolved)
        self.assertEqual(
            quarantine.unresolved(source_code="NSA")[0].id,
            item.id,
        )

        resolved = quarantine.resolve(item.id, note="manual review completed")
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(quarantine.unresolved(source_code="NSA"), [])


class TransactionalOutboxSchemaTest(unittest.TestCase):
    def migrate(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            connection.executescript(path.read_text(encoding="utf-8"))
        return connection

    def test_outbox_dedupe_key_is_unique(self):
        connection = self.migrate()
        row = (
            "e1",
            "SEARCH_REINDEX_REQUIRED",
            "GrantCallVersion",
            "v1",
            "{}",
            "search:v1",
            "PENDING",
            0,
            "2026-09-23T00:00:00Z",
            "2026-09-23T00:00:00Z",
        )
        connection.execute(
            "INSERT INTO outbox_events("
            "id,event_type,aggregate_type,aggregate_id,payload_json,dedupe_key,"
            "status,attempts,available_at,created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            row,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO outbox_events("
                "id,event_type,aggregate_type,aggregate_id,payload_json,dedupe_key,"
                "status,attempts,available_at,created_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("e2",) + row[1:],
            )

    def test_canonical_write_and_outbox_can_rollback_atomically(self):
        connection = self.migrate()
        connection.isolation_level = None
        connection.execute("BEGIN")
        try:
            connection.execute(
                "INSERT INTO providers(id,name,provider_type) "
                "VALUES ('p1','Provider','NATIONAL')"
            )
            connection.execute(
                "INSERT INTO outbox_events("
                "id,event_type,aggregate_type,aggregate_id,payload_json,dedupe_key,"
                "status,attempts,available_at,created_at"
                ") VALUES ("
                "'e1','SEARCH_REINDEX_REQUIRED','Provider','p1','{}','provider:p1',"
                "'PENDING',0,'2026-09-23T00:00:00Z','2026-09-23T00:00:00Z'"
                ")"
            )
            raise RuntimeError("simulate failure after both writes")
        except RuntimeError:
            connection.execute("ROLLBACK")

        providers = connection.execute(
            "SELECT COUNT(*) FROM providers WHERE id='p1'"
        ).fetchone()[0]
        events = connection.execute(
            "SELECT COUNT(*) FROM outbox_events WHERE id='e1'"
        ).fetchone()[0]
        self.assertEqual(providers, 0)
        self.assertEqual(events, 0)


if __name__ == "__main__":
    unittest.main()
