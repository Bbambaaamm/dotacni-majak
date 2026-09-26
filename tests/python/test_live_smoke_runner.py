"""Unit tests for the unified live-source smoke runner.

Tests are stdlib-only: they load scripts/live_smoke_runners.py via importlib
and exercise the manifest validation, result aggregation, formatting, and
UNKNOWN-vs-FAIL semantics — without importing pydantic/httpx.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "live_smoke_runners.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location(
        "dotacni_majak_live_smoke_runners_under_test", RUNNER_PATH
    )
    if spec is None:
        raise ImportError(f"cannot create import spec for {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["dotacni_majak_live_smoke_runners_under_test"] = module
    spec.loader.exec_module(module)
    return module


M = _load_runner_module()


class SmokeStatusTest(unittest.TestCase):
    def test_has_four_states(self):
        values = {s.value for s in M.SmokeStatus}
        self.assertEqual(values, {"HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"})

    def test_unknown_is_distinct_from_unavailable(self):
        self.assertNotEqual(
            M.SmokeStatus.UNKNOWN.value, M.SmokeStatus.UNAVAILABLE.value
        )


class SmokeTargetTest(unittest.TestCase):
    def test_target_fields(self):
        t = M.SmokeTarget("TEST", "Test Source", "mod", "Cls", "connectors/test")
        self.assertEqual(t.source_code, "TEST")
        self.assertEqual(t.source_name, "Test Source")
        self.assertEqual(t.adapter_module, "mod")
        self.assertEqual(t.adapter_class, "Cls")
        self.assertEqual(t.connector_path, "connectors/test")


class SmokeResultTest(unittest.TestCase):
    def test_required_fields(self):
        r = M.SmokeResult(
            source_code="EU_FT",
            source_name="EU Funding",
            status="HEALTHY",
            checked_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(r.status, "HEALTHY")
        self.assertIsNone(r.detail)
        self.assertIsNone(r.error)
        self.assertIsNone(r.discovered_count)
        self.assertIsNone(r.adapter_version)

    def test_all_fields(self):
        r = M.SmokeResult(
            source_code="EU_FT",
            source_name="EU Funding",
            status="DEGRADED",
            detail="health degraded",
            error="timeout",
            discovered_count=3,
            adapter_version="0.1.0",
            checked_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(r.discovered_count, 3)
        self.assertEqual(r.adapter_version, "0.1.0")
        self.assertEqual(r.error, "timeout")


class ValidateTargetsTest(unittest.TestCase):
    def test_live_manifest_is_valid(self):
        errors = M.validate_targets(M.SMOKE_TARGETS)
        self.assertEqual(errors, [], f"manifest validation errors: {errors}")

    def test_no_duplicate_source_codes(self):
        codes = [t.source_code for t in M.SMOKE_TARGETS]
        self.assertEqual(len(codes), len(set(codes)), f"duplicate codes: {codes}")

    def test_manifest_is_non_empty(self):
        self.assertGreater(len(M.SMOKE_TARGETS), 10)

    def test_all_modules_are_valid_identifiers(self):
        for t in M.SMOKE_TARGETS:
            self.assertTrue(
                t.adapter_module.isidentifier(),
                f"invalid adapter_module: {t.adapter_module}",
            )

    def test_all_classes_are_valid_identifiers(self):
        for t in M.SMOKE_TARGETS:
            self.assertTrue(
                t.adapter_class.isidentifier(),
                f"invalid adapter_class: {t.adapter_class}",
            )

    def test_all_connector_paths_exist(self):
        for t in M.SMOKE_TARGETS:
            p = ROOT / t.connector_path
            self.assertTrue(p.is_dir(), f"connector path missing: {t.connector_path}")

    def test_rejects_duplicate_source_code(self):
        targets = [
            M.SmokeTarget("X", "X", "mod", "Adapter", "c/x"),
            M.SmokeTarget("X", "X", "mod", "Adapter", "c/x"),
        ]
        errors = M.validate_targets(targets)
        self.assertTrue(any("duplicate source_code" in e for e in errors))

    def test_rejects_invalid_module_name(self):
        targets = [
            M.SmokeTarget("X", "X", "bad-module!", "Adapter", "c/x"),
        ]
        errors = M.validate_targets(targets)
        self.assertTrue(any("invalid adapter_module" in e for e in errors))

    def test_rejects_empty_source_name(self):
        targets = [
            M.SmokeTarget("X", "", "mod", "Adapter", "c/x"),
        ]
        errors = M.validate_targets(targets)
        self.assertTrue(any("empty source_name" in e for e in errors))


class AggregateResultsTest(unittest.TestCase):
    def _mk(self, code, status):
        return M.SmokeResult(
            source_code=code,
            source_name="Test",
            status=status,
            checked_at="2026-01-01T00:00:00Z",
        )

    def test_empty_results(self):
        summary = M.aggregate_results([])
        self.assertEqual(summary.total, 0)
        self.assertEqual(summary.healthy, 0)
        self.assertEqual(summary.degraded, 0)
        self.assertEqual(summary.unavailable, 0)
        self.assertEqual(summary.unknown, 0)
        self.assertEqual(summary.blocking_sources, [])

    def test_mixed_results(self):
        results = [
            self._mk("A", "HEALTHY"),
            self._mk("B", "HEALTHY"),
            self._mk("C", "DEGRADED"),
            self._mk("D", "UNAVAILABLE"),
            self._mk("E", "UNKNOWN"),
        ]
        summary = M.aggregate_results(results)
        self.assertEqual(summary.total, 5)
        self.assertEqual(summary.healthy, 2)
        self.assertEqual(summary.degraded, 1)
        self.assertEqual(summary.unavailable, 1)
        self.assertEqual(summary.unknown, 1)
        self.assertEqual(set(summary.blocking_sources), {"D", "E"})

    def test_all_healthy(self):
        results = [self._mk(f"S{i}", "HEALTHY") for i in range(10)]
        summary = M.aggregate_results(results)
        self.assertEqual(summary.healthy, 10)
        self.assertEqual(summary.blocking_sources, [])

    def test_unknown_status_treated_as_unknown(self):
        """An unrecognized status string is classified as UNKNOWN."""
        results = [self._mk("X", "BOGUS_STATUS")]
        summary = M.aggregate_results(results)
        self.assertEqual(summary.unknown, 1)
        self.assertIn("X", summary.blocking_sources)

    def test_unknown_not_treated_as_failure(self):
        """UNKNOWN is surfaced in counts but is a distinct state, not silently FAILED."""
        results = [self._mk("X", "UNKNOWN")]
        summary = M.aggregate_results(results)
        self.assertEqual(summary.healthy, 0)
        self.assertEqual(summary.unknown, 1)
        self.assertIn("X", summary.blocking_sources)


class HasBlockingFailuresTest(unittest.TestCase):
    def _summary(self, **kw):
        defaults = dict(total=0, healthy=0, degraded=0, unavailable=0, unknown=0, blocking_sources=[])
        defaults.update(kw)
        return M.SmokeSummary(**defaults)

    def test_no_blocking_when_all_healthy(self):
        s = self._summary(total=3, healthy=3)
        self.assertFalse(M.has_blocking_failures(s))

    def test_degraded_not_blocking(self):
        s = self._summary(total=3, healthy=2, degraded=1)
        self.assertFalse(M.has_blocking_failures(s))

    def test_unavailable_is_blocking(self):
        s = self._summary(total=3, healthy=2, unavailable=1, blocking_sources=["X"])
        self.assertTrue(M.has_blocking_failures(s))

    def test_unknown_is_blocking(self):
        s = self._summary(total=3, healthy=2, unknown=1, blocking_sources=["Y"])
        self.assertTrue(M.has_blocking_failures(s))

    def test_mixed_is_blocking(self):
        s = self._summary(
            total=4, healthy=1, degraded=1, unavailable=1, unknown=1,
            blocking_sources=["X", "Y"],
        )
        self.assertTrue(M.has_blocking_failures(s))


class FormatResultsTest(unittest.TestCase):
    def test_produces_human_readable_and_json(self):
        results = [
            M.SmokeResult(
                source_code="EU_FT",
                source_name="EU Funding",
                status="HEALTHY",
                detail="health: HEALTHY; discovered: 5",
                discovered_count=5,
                adapter_version="0.1.0",
                checked_at="2026-01-01T00:00:00Z",
            ),
            M.SmokeResult(
                source_code="BAD_SRC",
                source_name="Bad Source",
                status="UNKNOWN",
                error="unexpected error: ConnectionError",
                checked_at="2026-01-01T00:01:00Z",
            ),
        ]
        summary = M.aggregate_results(results)
        output = M.format_results(results, summary)

        self.assertIn("[HEALTHY] EU_FT (EU Funding)", output)
        self.assertIn("discovered: 5", output)
        self.assertIn("[UNKNOWN] BAD_SRC (Bad Source)", output)
        self.assertIn("unexpected error", output)
        self.assertIn("Blocking sources: BAD_SRC", output)
        self.assertIn("```json", output)

    def test_json_contains_all_fields(self):
        results = [
            M.SmokeResult(
                source_code="EU_FT",
                source_name="EU Funding",
                status="HEALTHY",
                discovered_count=3,
                checked_at="2026-01-01T00:00:00Z",
            ),
        ]
        summary = M.aggregate_results(results)
        output = M.format_results(results, summary)

        # Extract JSON from fenced block
        start = output.index("```json") + 7
        end = output.index("```", start)
        data = json.loads(output[start:end].strip())
        self.assertIn("summary", data)
        self.assertIn("results", data)
        self.assertEqual(data["summary"]["total"], 1)
        self.assertEqual(data["summary"]["healthy"], 1)
        self.assertEqual(data["results"][0]["source_code"], "EU_FT")
        self.assertEqual(data["results"][0]["discovered_count"], 3)

    def test_empty_results_format(self):
        summary = M.aggregate_results([])
        output = M.format_results([], summary)
        self.assertIn("Total: 0", output)
        self.assertIn("No blocking failures.", output)


class ExitCodeLogicTest(unittest.TestCase):
    """Verify the exit-code contract without running the full async runner."""

    def _results(self, statuses):
        return [
            M.SmokeResult(
                source_code=f"S{i}",
                source_name="Test",
                status=s,
                checked_at="2026-01-01T00:00:00Z",
            )
            for i, s in enumerate(statuses)
        ]

    def test_exit_zero_for_healthy_degraded(self):
        results = self._results(["HEALTHY", "DEGRADED", "HEALTHY"])
        summary = M.aggregate_results(results)
        self.assertFalse(M.has_blocking_failures(summary))

    def test_exit_one_for_unavailable(self):
        results = self._results(["HEALTHY", "UNAVAILABLE"])
        summary = M.aggregate_results(results)
        self.assertTrue(M.has_blocking_failures(summary))

    def test_exit_one_for_unknown(self):
        results = self._results(["HEALTHY", "UNKNOWN"])
        summary = M.aggregate_results(results)
        self.assertTrue(M.has_blocking_failures(summary))

    def test_exit_zero_all_healthy(self):
        results = self._results(["HEALTHY"] * 27)
        summary = M.aggregate_results(results)
        self.assertFalse(M.has_blocking_failures(summary))


if __name__ == "__main__":
    unittest.main()
