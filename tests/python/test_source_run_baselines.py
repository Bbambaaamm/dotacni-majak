import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.data_quality import (  # noqa: E402
    QualityGateStatus,
    SourceRunObservation,
    SourceRunQualityGate,
)
from dotacni_majak_ingestion.source_run_baselines import (
    BaselineConfig,
    InMemorySourceRunBaselineRepository,
    RollingBaselineCalculator,
    SourceRunBaseline,
    SourceRunRecord,
    SqliteSourceRunBaselineRepository,
)

UTC = timezone.utc
T0 = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)


def _run(
    run_id: str,
    started_at: datetime,
    *,
    records_seen: int,
    error_count: int = 0,
    adapter_version: str = "v1",
    status: str = "COMPLETED",
    finished_offset: timedelta | None = timedelta(seconds=60),
) -> SourceRunRecord:
    finished_at = (
        None if finished_offset is None else started_at + finished_offset
    )
    return SourceRunRecord(
        source_code="NSA",
        id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        records_seen=records_seen,
        error_count=error_count,
        adapter_version=adapter_version,
    )


def _migrate(connection: sqlite3.Connection) -> None:
    paths = sorted((ROOT / "migrations").glob("*.sql"))
    assert paths, "No migrations found"
    for path in paths:
        connection.executescript(path.read_text(encoding="utf-8"))


class RollingBaselineCalculatorTest(unittest.TestCase):
    def setUp(self):
        self.calculator = RollingBaselineCalculator()

    def _runs(self, counts, *, version="v1"):
        return [
            _run(f"r{i}", T0 + timedelta(minutes=i), records_seen=c, adapter_version=version)
            for i, c in enumerate(counts)
        ]

    def test_rolling_median_odd_window(self):
        baseline = self.calculator.compute(
            "NSA", self._runs([100, 200, 300, 400, 500]),
            adapter_version="v1", now=T0,
        )
        self.assertFalse(baseline.is_bootstrapped)
        self.assertEqual(baseline.sample_count, 5)
        # window_size=10 > 5 runs, so all 5 are used; median of [100..500] = 300
        self.assertEqual(baseline.median_records, 300.0)

    def test_window_size_limits_lookback(self):
        calc = RollingBaselineCalculator(BaselineConfig(window_size=3, min_samples=2))
        baseline = calc.compute(
            "NSA", self._runs([10, 20, 30, 40, 50]),
            adapter_version="v1", now=T0,
        )
        # Only the 3 newest runs (30, 40, 50) are in the window; median = 40.
        self.assertEqual(baseline.sample_count, 3)
        self.assertEqual(baseline.median_records, 40.0)

    def test_window_selection_is_independent_of_input_order(self):
        runs = self._runs([10, 20, 30, 40, 50])
        ordered = self.calculator.compute("NSA", runs, adapter_version="v1", now=T0)
        reversed_runs = list(reversed(runs))
        other = self.calculator.compute("NSA", reversed_runs, adapter_version="v1", now=T0)
        self.assertEqual(ordered, other)

    def test_even_window_median_is_average_of_two_middle(self):
        calc = RollingBaselineCalculator(BaselineConfig(window_size=4, min_samples=4))
        baseline = calc.compute(
            "NSA", self._runs([100, 200, 300, 400]),
            adapter_version="v1", now=T0,
        )
        self.assertEqual(baseline.median_records, 250.0)

    def test_bootstrap_when_fewer_than_min_samples(self):
        calc = RollingBaselineCalculator(BaselineConfig(window_size=10, min_samples=3))
        baseline = calc.compute(
            "NSA", self._runs([100, 200]),
            adapter_version="v1", now=T0,
        )
        self.assertTrue(baseline.is_bootstrapped)
        self.assertEqual(baseline.sample_count, 2)
        self.assertIsNone(baseline.median_records)
        self.assertIsNone(baseline.mean_error_rate)
        self.assertIsNone(baseline.mean_success_rate)

    def test_empty_run_history_is_bootstrapped_and_safe(self):
        baseline = self.calculator.compute(
            "NSA", [], adapter_version="v1", now=T0,
        )
        self.assertTrue(baseline.is_bootstrapped)
        self.assertEqual(baseline.sample_count, 0)
        self.assertIsNone(baseline.median_records)

    def test_first_run_without_baseline_is_not_assumed_broken(self):
        # A freshly reset / first run yields an UNKNOWN baseline; the quality
        # gate must NOT degrade a source that simply lacks history.
        baseline = self.calculator.compute("NSA", [], adapter_version="v1", now=T0)
        observation = self.calculator.to_observation(
            baseline, records_found=0,
        )
        decision = SourceRunQualityGate().evaluate(observation)
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)
        self.assertTrue(decision.destructive_changes_allowed)

    def test_source_version_reset_excludes_old_version_runs(self):
        calc = RollingBaselineCalculator(BaselineConfig(window_size=10, min_samples=3))
        runs = self._runs([1000, 1100, 1200], version="v1") + self._runs(
            [10, 20, 30], version="v2"
        )
        baseline = calc.compute("NSA", runs, adapter_version="v2", now=T0)
        # The v1 runs (1000-1200) must NOT contribute; only v2 runs (10,20,30).
        self.assertEqual(baseline.sample_count, 3)
        self.assertEqual(baseline.median_records, 20.0)
        self.assertFalse(baseline.is_bootstrapped)

    def test_version_change_with_too_few_runs_bootstraps(self):
        calc = RollingBaselineCalculator(BaselineConfig(window_size=10, min_samples=3))
        # Old version has a stable baseline; new version has only 1 run so far.
        runs = self._runs([100, 200, 300], version="v1") + self._runs(
            [5], version="v2"
        )
        baseline = calc.compute("NSA", runs, adapter_version="v2", now=T0)
        self.assertTrue(baseline.is_bootstrapped)
        self.assertEqual(baseline.sample_count, 1)
        self.assertIsNone(baseline.median_records)

    def test_locked_and_unfinished_runs_are_excluded(self):
        runs = [
            _run("a", T0 - timedelta(hours=3), records_seen=100),
            _run("b", T0 - timedelta(hours=2), records_seen=200, status="LOCKED"),
            _run("c", T0 - timedelta(hours=1), records_seen=300, finished_offset=None),
            _run("d", T0, records_seen=400),
        ]
        baseline = self.calculator.compute(
            "NSA", runs, adapter_version="v1", now=T0,
        )
        # Only runs a and d are usable -> 2 samples (< min_samples 3) -> bootstrap.
        self.assertTrue(baseline.is_bootstrapped)
        self.assertEqual(baseline.sample_count, 2)

    def test_error_and_success_rate_baseline(self):
        calc = RollingBaselineCalculator(BaselineConfig(window_size=3, min_samples=2))
        runs = [
            _run("a", T0, records_seen=100, error_count=10),  # 0.10
            _run("b", T0 + timedelta(hours=1), records_seen=200, error_count=20),  # 0.10
            _run("c", T0 + timedelta(hours=2), records_seen=100, error_count=0),  # 0.0
        ]
        baseline = calc.compute("NSA", runs, adapter_version="v1", now=T0)
        self.assertFalse(baseline.is_bootstrapped)
        self.assertEqual(baseline.sample_count, 3)
        self.assertAlmostEqual(baseline.mean_error_rate, (0.1 + 0.1 + 0.0) / 3)
        self.assertAlmostEqual(baseline.mean_success_rate, 1.0 - baseline.mean_error_rate)

    def test_deterministic_across_computation_calls(self):
        runs = self._runs([100, 200, 300, 400])
        first = self.calculator.compute("NSA", runs, adapter_version="v1", now=T0)
        second = self.calculator.compute("NSA", runs, adapter_version="v1", now=T0)
        self.assertEqual(first, second)

    def test_to_observation_maps_baseline_fields(self):
        runs = self._runs([100, 200, 300])
        baseline = self.calculator.compute("NSA", runs, adapter_version="v1", now=T0)
        obs = self.calculator.to_observation(
            baseline, records_found=5, http_requests=10, http_errors=1,
            parse_attempts=5, parse_failures=1,
        )
        self.assertEqual(obs.records_found, 5)
        self.assertEqual(obs.baseline_samples, baseline.sample_count)
        self.assertEqual(obs.baseline_median_records, baseline.median_records)
        self.assertEqual(obs.http_errors, 1)
        self.assertEqual(obs.parse_failures, 1)

    def test_record_count_collapse_degrades_when_below_baseline(self):
        # Stable baseline at ~120 records; a run returning 0 triggers the gate.
        runs = self._runs([110, 120, 130, 115, 125])
        baseline = self.calculator.compute("NSA", runs, adapter_version="v1", now=T0)
        observation = self.calculator.to_observation(
            baseline, records_found=0,
        )
        self.assertEqual(observation.baseline_samples, baseline.sample_count)
        self.assertEqual(
            observation.baseline_median_records, baseline.median_records
        )
        decision = SourceRunQualityGate().evaluate(observation)
        self.assertEqual(decision.status, QualityGateStatus.DEGRADED)
        self.assertFalse(decision.destructive_changes_allowed)
        self.assertIn(
            "RECORD_COUNT_COLLAPSE",
            {v.code for v in decision.violations},
        )

    def test_stable_zero_baseline_does_not_false_positive(self):
        # A source that consistently reports 0 records has a 0 median; a 0-record
        # run is then normal (gate only flags collapse when median > 0).
        runs = self._runs([0, 0, 0])
        baseline = self.calculator.compute("NSA", runs, adapter_version="v1", now=T0)
        observation = self.calculator.to_observation(
            baseline, records_found=0,
        )
        decision = SourceRunQualityGate().evaluate(observation)
        self.assertEqual(decision.status, QualityGateStatus.HEALTHY)


class InMemoryBaselineRepositoryTest(unittest.TestCase):
    def test_upsert_and_get_roundtrip_idempotent(self):
        repo = InMemorySourceRunBaselineRepository()
        baseline = SourceRunBaseline(
            source_code="NSA", adapter_version="v1", computed_at=T0,
            sample_count=3, median_records=200.0, mean_error_rate=0.1,
            mean_success_rate=0.9, is_bootstrapped=False,
        )
        repo.upsert_baseline(baseline)
        repo.upsert_baseline(baseline)  # idempotent: no duplicate, same value
        self.assertEqual(repo.get_baseline("NSA"), baseline)

    def test_get_baseline_missing_returns_none(self):
        repo = InMemorySourceRunBaselineRepository()
        self.assertIsNone(repo.get_baseline("NSA"))

    def test_list_recent_runs_orders_desc_and_filters_version(self):
        repo = InMemorySourceRunBaselineRepository()
        for c in (100, 200, 300):
            repo.add_run(_run(f"r{c}", T0 + timedelta(hours=c / 100), records_seen=c))
        recent = repo.list_recent_runs("NSA", adapter_version="v1", limit=10)
        self.assertEqual([r.records_seen for r in recent], [300, 200, 100])


class SqliteBaselineRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        _migrate(self.connection)
        self.connection.execute(
            "INSERT INTO source_registry"
            "(id, code, name, base_url, adapter_key, authority, retrieval_mode, refresh_minutes)"
            " VALUES ('src-1','NSA','NSA','https://nsa.gov.cz','nsa','OFFICIAL','API',60)"
        )
        self.connection.commit()
        self.repo = SqliteSourceRunBaselineRepository(self.connection)

    def _insert_run(self, run_id, started_at, *, records, errors=0, version="v1",
                    status="COMPLETED", finished=None):
        self.connection.execute(
            "INSERT INTO source_runs"
            "(id, source_id, started_at, finished_at, status, records_seen,"
            " new_records, changed_records, error_count, adapter_version)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (
                run_id, "src-1", started_at.isoformat(),
                (finished or started_at + timedelta(seconds=60)).isoformat(),
                status, records, errors, version,
            ),
        )
        self.connection.commit()

    def test_list_recent_runs_returns_version_filtered_finished_runs(self):
        self._insert_run("a", T0, records=100, version="v1")
        self._insert_run("b", T0 + timedelta(hours=1), records=200, version="v1")
        self._insert_run("c", T0 + timedelta(hours=2), records=300, version="v2")
        recent = self.repo.list_recent_runs("NSA", adapter_version="v2", limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].id, "c")
        self.assertEqual(recent[0].source_code, "NSA")

    def test_upsert_and_get_baseline_roundtrip_is_idempotent(self):
        baseline = SourceRunBaseline(
            source_code="NSA", adapter_version="v2", computed_at=T0,
            sample_count=3, median_records=150.0, mean_error_rate=0.05,
            mean_success_rate=0.95, is_bootstrapped=False,
        )
        self.repo.upsert_baseline(baseline)
        self.repo.upsert_baseline(baseline)  # idempotent upsert
        loaded = self.repo.get_baseline("NSA")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.adapter_version, "v2")
        self.assertEqual(loaded.sample_count, 3)
        self.assertEqual(loaded.median_records, 150.0)
        self.assertEqual(loaded.mean_error_rate, 0.05)
        self.assertEqual(loaded.mean_success_rate, 0.95)
        self.assertFalse(loaded.is_bootstrapped)
        # Exactly one row persisted despite two upserts.
        count = self.connection.execute(
            "SELECT COUNT(*) FROM source_run_baselines WHERE source_id='src-1'"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_bootstrapped_baseline_persists_null_signals(self):
        baseline = SourceRunBaseline(
            source_code="NSA", adapter_version="v3", computed_at=T0,
            sample_count=1, median_records=None, mean_error_rate=None,
            mean_success_rate=None, is_bootstrapped=True,
        )
        self.repo.upsert_baseline(baseline)
        loaded = self.repo.get_baseline("NSA")
        self.assertTrue(loaded.is_bootstrapped)
        self.assertIsNone(loaded.median_records)

    def test_end_to_end_compute_persists_and_feeds_gate(self):
        for i, c in enumerate([100, 200, 300]):
            self._insert_run(f"r{i}", T0 + timedelta(hours=i), records=c, version="v1")
        runs = self.repo.list_recent_runs("NSA", adapter_version="v1", limit=10)
        baseline = RollingBaselineCalculator().compute(
            "NSA", runs, adapter_version="v1", now=T0 + timedelta(hours=9),
        )
        self.assertFalse(baseline.is_bootstrapped)
        self.assertEqual(baseline.median_records, 200.0)
        self.repo.upsert_baseline(baseline)
        loaded = self.repo.get_baseline("NSA")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.median_records, 200.0)

    def test_unknown_source_raises_no_silent_false_signal(self):
        with self.assertRaises(KeyError):
            self.repo.list_recent_runs("NOPE", adapter_version="v1", limit=10)


if __name__ == "__main__":
    unittest.main()
