import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.data_quality import QualityGateStatus
from dotacni_majak_ingestion.health import (
    HealthReason,
    ScheduleHealthInput,
    SourceHealthEvaluator,
    SourceHealthStatus,
)


NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


class SourceHealthEvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.evaluator = SourceHealthEvaluator()

    def test_recent_success_and_run_is_healthy(self):
        snapshot = self.evaluator.evaluate(
            source_code="NSA",
            now=NOW,
            schedule=ScheduleHealthInput(
                expected_interval=HOUR,
                last_expected_run_at=NOW - timedelta(minutes=5),
                last_actual_run_at=NOW - timedelta(minutes=4),
                last_success_at=NOW - timedelta(minutes=4),
            ),
            quality_status=QualityGateStatus.HEALTHY,
        )
        self.assertEqual(snapshot.status, SourceHealthStatus.HEALTHY)
        self.assertEqual(snapshot.reasons, ())
        self.assertFalse(snapshot.serves_last_known_good)

    def test_missed_recent_run_is_degraded_not_silently_healthy(self):
        snapshot = self.evaluator.evaluate(
            source_code="NSA",
            now=NOW,
            schedule=ScheduleHealthInput(
                expected_interval=HOUR,
                last_expected_run_at=NOW - timedelta(minutes=30),
                last_actual_run_at=NOW - timedelta(hours=1, minutes=20),
                last_success_at=NOW - timedelta(hours=1, minutes=20),
                grace_period=timedelta(minutes=10),
            ),
            quality_status=QualityGateStatus.HEALTHY,
        )
        self.assertEqual(snapshot.status, SourceHealthStatus.DEGRADED)
        self.assertIn(HealthReason.SCHEDULED_RUN_MISSED, snapshot.reasons)
        self.assertTrue(snapshot.serves_last_known_good)

    def test_stale_success_is_unavailable(self):
        snapshot = self.evaluator.evaluate(
            source_code="NSA",
            now=NOW,
            schedule=ScheduleHealthInput(
                expected_interval=HOUR,
                last_expected_run_at=NOW - timedelta(minutes=5),
                last_actual_run_at=NOW - timedelta(minutes=4),
                last_success_at=NOW - timedelta(hours=5),
                grace_period=timedelta(minutes=5),
                unavailable_after_intervals=3,
            ),
            quality_status=QualityGateStatus.HEALTHY,
        )
        self.assertEqual(snapshot.status, SourceHealthStatus.UNAVAILABLE)
        self.assertIn(HealthReason.LAST_SUCCESS_STALE, snapshot.reasons)

    def test_quality_gate_degrades_source(self):
        snapshot = self.evaluator.evaluate(
            source_code="NSA",
            now=NOW,
            schedule=ScheduleHealthInput(
                expected_interval=HOUR,
                last_expected_run_at=NOW - timedelta(minutes=5),
                last_actual_run_at=NOW - timedelta(minutes=4),
                last_success_at=NOW - timedelta(minutes=4),
            ),
            quality_status=QualityGateStatus.DEGRADED,
        )
        self.assertEqual(snapshot.status, SourceHealthStatus.DEGRADED)
        self.assertIn(
            HealthReason.QUALITY_GATE_DEGRADED,
            snapshot.reasons,
        )

    def test_direct_healthcheck_failure_is_unavailable(self):
        snapshot = self.evaluator.evaluate(
            source_code="NSA",
            now=NOW,
            schedule=ScheduleHealthInput(
                expected_interval=HOUR,
                last_expected_run_at=NOW - timedelta(minutes=5),
                last_actual_run_at=NOW - timedelta(minutes=4),
                last_success_at=NOW - timedelta(minutes=4),
            ),
            quality_status=QualityGateStatus.HEALTHY,
            direct_healthcheck_available=False,
        )
        self.assertEqual(snapshot.status, SourceHealthStatus.UNAVAILABLE)
        self.assertIn(
            HealthReason.DIRECT_HEALTHCHECK_UNAVAILABLE,
            snapshot.reasons,
        )

    def test_never_run_is_degraded_not_false_unavailable(self):
        snapshot = self.evaluator.evaluate(
            source_code="NEW",
            now=NOW,
            schedule=ScheduleHealthInput(
                expected_interval=HOUR,
                last_expected_run_at=None,
                last_actual_run_at=None,
                last_success_at=None,
            ),
            quality_status=None,
        )
        self.assertEqual(snapshot.status, SourceHealthStatus.DEGRADED)
        self.assertIn(HealthReason.NEVER_RUN, snapshot.reasons)


if __name__ == "__main__":
    unittest.main()
