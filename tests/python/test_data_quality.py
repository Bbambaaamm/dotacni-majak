import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.data_quality import (
    QualityGateConfig,
    QualityGateStatus,
    SourceRunObservation,
    SourceRunQualityGate,
)


class SourceRunQualityGateTest(unittest.TestCase):
    def test_healthy_run_allows_destructive_changes(self):
        gate = SourceRunQualityGate()
        decision = gate.evaluate(
            SourceRunObservation(
                records_found=120,
                baseline_samples=5,
                baseline_median_records=118,
                http_requests=100,
                http_errors=1,
                parse_attempts=120,
                parse_failures=1,
                validation_attempts=119,
                validation_failures=1,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)
        self.assertEqual(decision.violations, ())

    def test_record_count_collapse_degrades_and_blocks_destructive_changes(self):
        gate = SourceRunQualityGate(
            QualityGateConfig(min_baseline_samples=3, min_records_ratio=0.35)
        )
        decision = gate.evaluate(
            SourceRunObservation(
                records_found=4,
                baseline_samples=7,
                baseline_median_records=120,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)
        self.assertIn(
            "RECORD_COUNT_COLLAPSE",
            {violation.code for violation in decision.violations},
        )

    def test_structure_change_degrades_even_without_baseline(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=10,
                unexpected_structure_change=True,
            )
        )
        self.assertTrue(decision.is_degraded)
        self.assertFalse(decision.destructive_changes_allowed)
        self.assertIn(
            "UNEXPECTED_STRUCTURE_CHANGE",
            {violation.code for violation in decision.violations},
        )

    def test_high_http_parse_and_validation_error_rates_are_reported(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=100,
                http_requests=10,
                http_errors=4,
                parse_attempts=10,
                parse_failures=3,
                validation_attempts=10,
                validation_failures=3,
            )
        )
        codes = {violation.code for violation in decision.violations}
        self.assertEqual(
            codes,
            {
                "HTTP_ERROR_RATE_HIGH",
                "PARSE_SUCCESS_LOW",
                "VALIDATION_SUCCESS_LOW",
            },
        )
        self.assertFalse(decision.destructive_changes_allowed)

    def test_small_baseline_does_not_trigger_count_collapse(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=0,
                baseline_samples=2,
                baseline_median_records=100,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)

    def test_invalid_observation_counters_are_rejected(self):
        with self.assertRaises(ValueError):
            SourceRunObservation(
                records_found=1,
                http_requests=1,
                http_errors=2,
            )


if __name__ == "__main__":
    unittest.main()
