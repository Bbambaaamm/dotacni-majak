import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.quality import SourceRunMetrics, SourceRunQuality, SourceRunQualityGate
from dotacni_majak_ingestion.quarantine import DataQualityIssue, DataQualitySeverity, ValidationResult
from dotacni_majak_ingestion.outbox import OutboxEvent, OutboxEventType


class QualityGateTest(unittest.TestCase):
    def test_zero_records_against_stable_history_is_degraded(self):
        gate = SourceRunQualityGate()
        history = [SourceRunMetrics(records_found=x) for x in (100, 110, 105)]
        decision = gate.evaluate(SourceRunMetrics(records_found=0), history)
        self.assertEqual(decision.status, SourceRunQuality.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)
        self.assertIn("records_found_anomaly", decision.reasons)

    def test_high_parse_error_rate_is_degraded_without_history(self):
        gate = SourceRunQualityGate()
        decision = gate.evaluate(SourceRunMetrics(records_found=10, parse_error_rate=0.5), [])
        self.assertEqual(decision.status, SourceRunQuality.DEGRADED)

    def test_normal_run_is_healthy(self):
        gate = SourceRunQualityGate()
        history = [SourceRunMetrics(records_found=x) for x in (100, 100, 100)]
        decision = gate.evaluate(SourceRunMetrics(records_found=95), history)
        self.assertEqual(decision.status, SourceRunQuality.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)


class ValidationResultTest(unittest.TestCase):
    def test_error_blocks_publish(self):
        result = ValidationResult(issues=[DataQualityIssue(code="deadline.invalid", message="invalid deadline", severity=DataQualitySeverity.ERROR)])
        self.assertFalse(result.publishable)

    def test_warning_allows_publish(self):
        result = ValidationResult(issues=[DataQualityIssue(code="title.short", message="short title", severity=DataQualitySeverity.WARNING)])
        self.assertTrue(result.publishable)


class OutboxTest(unittest.TestCase):
    def test_payload_serialization_is_deterministic(self):
        event = OutboxEvent(
            event_type=OutboxEventType.SEARCH_REINDEX_REQUIRED,
            aggregate_type="grant_call_version",
            aggregate_id="v1",
            payload={"b": 2, "a": 1},
        )
        self.assertEqual(event.payload_json(), '{"a":1,"b":2}')


if __name__ == "__main__":
    unittest.main()
