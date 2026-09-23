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
    def test_record_count_collapse_degrades_and_blocks_destructive_changes(self):
        gate = SourceRunQualityGate(
            QualityGateConfig(
                min_baseline_samples=3,
                min_records_ratio=0.35,
            )
        )
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
            {v.code for v in decision.violations},
        )

    def test_healthy_run_allows_destructive_reconciliation(self):
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

    def test_structure_change_is_always_degraded(self):
        decision = SourceRunQualityGate().evaluate(
            SourceRunObservation(
                records_found=120,
                unexpected_structure_change=True,
            )
        )
        self.assertTrue(decision.is_degraded)
        self.assertFalse(decision.destructive_changes_allowed)


if __name__ == "__main__":
    unittest.main()
