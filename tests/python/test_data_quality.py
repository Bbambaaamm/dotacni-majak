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


class SourceRunQualityGateTest(unittest.TestCase):
    def test_record_count_collapse_blocks_destructive_changes(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=0,
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

    def test_healthy_run_allows_destructive_changes(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=118,
                baseline_samples=7,
                baseline_median_records=120,
                http_requests=20,
                http_errors=0,
                parse_attempts=118,
                parse_failures=1,
                validation_attempts=117,
                validation_failures=1,
            )
        )
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)
        self.assertEqual(decision.violations, ())

    def test_structure_change_always_degrades_run(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=120,
                baseline_samples=7,
                baseline_median_records=120,
                unexpected_structure_change=True,
            )
        )
        self.assertTrue(decision.is_degraded)
        self.assertFalse(decision.destructive_changes_allowed)


if __name__ == "__main__":
    unittest.main()
