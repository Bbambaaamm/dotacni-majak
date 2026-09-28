from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median

from .data_quality import SourceRunObservation


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("baseline timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _utc_now_iso() -> str:
    return _utc().isoformat()


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    """Configuration for rolling baseline computation.

    ``window_size`` bounds the rolling window; ``min_samples`` is the bootstrap
    threshold — while fewer than ``min_samples`` same-version runs exist the
    baseline stays UNKNOWN (no record-count / rate signal) so the quality gate
    cannot be triggered by absence of history.
    """

    window_size: int = 10
    min_samples: int = 3

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be >= 1")
        if self.min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if self.min_samples > self.window_size:
            raise ValueError("min_samples cannot exceed window_size")


@dataclass(frozen=True, slots=True)
class SourceRunRecord:
    """A finished source run observation used to build the rolling baseline.

    Mirrors the persisted ``source_runs`` row; only finished, real-source runs
    (status != 'LOCKED') are expected to be supplied to the calculator.
    """

    source_code: str
    id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    records_seen: int
    error_count: int
    adapter_version: str

    def __post_init__(self) -> None:
        if self.records_seen < 0:
            raise ValueError("records_seen must be >= 0")
        if self.error_count < 0:
            raise ValueError("error_count must be >= 0")
        if self.error_count > self.records_seen:
            raise ValueError("error_count cannot exceed records_seen")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceRunBaseline:
    """Persisted rolling baseline for a single source.

    ``median_records`` and the rate fields are ``None`` while ``is_bootstrapped``
    is ``True`` (too few same-version runs). The quality gate treats a NULL
    baseline as "no signal" rather than "failed", so a first run or a freshly
    version-reset source is never assumed broken.
    """

    source_code: str
    adapter_version: str
    computed_at: datetime
    sample_count: int
    median_records: float | None
    mean_error_rate: float | None
    mean_success_rate: float | None
    is_bootstrapped: bool


class RollingBaselineCalculator:
    """Computes a deterministic, idempotent rolling baseline for a source.

    Implements the scope of issue #327:

    * **Rolling window/median** — the last ``window_size`` finished runs inform
      ``median_records`` and the mean error/success rates.
    * **Bootstrap semantics** — with fewer than ``min_samples`` same-version
      runs the baseline is UNKNOWN (all signal fields ``None``), so the quality
      gate stays in its fail-safe first-run behaviour.
    * **Source version reset** — only runs matching the current
      ``adapter_version`` are considered. A parser/connector upgrade therefore
      resets the baseline window instead of comparing apples to oranges.

    The calculator is pure: given the same inputs it always returns the same
    baseline, and an upsert of the result is idempotent.
    """

    def __init__(self, config: BaselineConfig | None = None) -> None:
        self.config = config or BaselineConfig()

    def _window(self, runs: Sequence[SourceRunRecord], adapter_version: str) -> list[SourceRunRecord]:
        # Source version reset: drop any run whose adapter_version does not match
        # the version we are baselining. A version change deliberately resets
        # the window so stale, incomparable counts never drive the gate.
        relevant = [
            run
            for run in runs
            if run.adapter_version == adapter_version
            and run.status != "LOCKED"
            and run.finished_at is not None
        ]
        # Deterministic ordering: newest started_at first, id as a stable
        # tiebreaker so equal-timestamp windows are reproducible.
        return sorted(relevant, key=lambda r: (r.started_at, r.id), reverse=True)

    def compute(
        self,
        source_code: str,
        runs: Sequence[SourceRunRecord],
        *,
        adapter_version: str,
        now: datetime,
    ) -> SourceRunBaseline:
        window = self._window(runs, adapter_version)[: self.config.window_size]
        sample_count = len(window)
        bootstrapped = sample_count < self.config.min_samples

        if bootstrapped or sample_count == 0:
            # Bootstrap / UNKNOWN state is safe: no signal, no degradation.
            return SourceRunBaseline(
                source_code=source_code,
                adapter_version=adapter_version,
                computed_at=_utc(now),
                sample_count=sample_count,
                median_records=None,
                mean_error_rate=None,
                mean_success_rate=None,
                is_bootstrapped=True,
            )

        records = [run.records_seen for run in window]
        error_rates = [
            (run.error_count / run.records_seen) if run.records_seen > 0 else 0.0
            for run in window
        ]
        mean_error_rate = sum(error_rates) / len(error_rates)
        return SourceRunBaseline(
            source_code=source_code,
            adapter_version=adapter_version,
            computed_at=_utc(now),
            sample_count=sample_count,
            median_records=float(median(records)),
            mean_error_rate=mean_error_rate,
            mean_success_rate=1.0 - mean_error_rate,
            is_bootstrapped=False,
        )

    def to_observation(
        self,
        baseline: SourceRunBaseline,
        *,
        records_found: int = 0,
        http_requests: int = 0,
        http_errors: int = 0,
        parse_attempts: int = 0,
        parse_failures: int = 0,
        validation_attempts: int = 0,
        validation_failures: int = 0,
        unexpected_structure_change: bool = False,
    ) -> SourceRunObservation:
        """Build a quality-gate observation carrying the persisted baseline.

        This is the explicit adapter between baseline storage and the gate: it
        populates ``baseline_samples`` / ``baseline_median_records`` (and the
        per-run signal fields the caller provides) so ``SourceRunQualityGate``
        never evaluates a run without its rolling context.
        """
        return SourceRunObservation(
            records_found=records_found,
            baseline_samples=baseline.sample_count,
            baseline_median_records=baseline.median_records,
            http_requests=http_requests,
            http_errors=http_errors,
            parse_attempts=parse_attempts,
            parse_failures=parse_failures,
            validation_attempts=validation_attempts,
            validation_failures=validation_failures,
            unexpected_structure_change=unexpected_structure_change,
        )


class SourceRunBaselineRepository(ABC):
    """Persistence for source-run baselines and the runs they are built from."""

    @abstractmethod
    def list_recent_runs(
        self,
        source_code: str,
        *,
        adapter_version: str,
        limit: int | None = None,
    ) -> list[SourceRunRecord]:
        raise NotImplementedError

    @abstractmethod
    def upsert_baseline(self, baseline: SourceRunBaseline) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_baseline(self, source_code: str) -> SourceRunBaseline | None:
        raise NotImplementedError


class InMemorySourceRunBaselineRepository(SourceRunBaselineRepository):
    """Reference repository for focused unit tests and local development."""

    def __init__(self) -> None:
        self.runs: dict[str, list[SourceRunRecord]] = {}
        self.baselines: dict[str, SourceRunBaseline] = {}

    def add_run(self, run: SourceRunRecord) -> None:
        self.runs.setdefault(run.source_code, []).append(run)

    def list_recent_runs(
        self,
        source_code: str,
        *,
        adapter_version: str,
        limit: int | None = None,
    ) -> list[SourceRunRecord]:
        runs = self.runs.get(source_code, [])
        window = self._window(runs, adapter_version)
        if limit is not None:
            window = window[:limit]
        return window

    @staticmethod
    def _window(runs: Sequence[SourceRunRecord], adapter_version: str) -> list[SourceRunRecord]:
        relevant = [
            run
            for run in runs
            if run.adapter_version == adapter_version
            and run.status != "LOCKED"
            and run.finished_at is not None
        ]
        return sorted(relevant, key=lambda r: (r.started_at, r.id), reverse=True)

    def upsert_baseline(self, baseline: SourceRunBaseline) -> None:
        self.baselines[baseline.source_code] = baseline

    def get_baseline(self, source_code: str) -> SourceRunBaseline | None:
        return self.baselines.get(source_code)


class SqliteSourceRunBaselineRepository(SourceRunBaselineRepository):
    """D1-compatible SQLite implementation.

    Reads finished, same-version runs from ``source_runs`` and persists the
    computed baseline in ``source_run_baselines``. Uses only the D1 SQL subset.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")

    def _source_id(self, source_code: str) -> str:
        row = self.connection.execute(
            "SELECT id FROM source_registry WHERE code = ?",
            (source_code,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown source_code {source_code!r}")
        return str(row[0])

    def list_recent_runs(
        self,
        source_code: str,
        *,
        adapter_version: str,
        limit: int | None = None,
    ) -> list[SourceRunRecord]:
        source_id = self._source_id(source_code)
        rows = self.connection.execute(
            """SELECT sr.id, sr.started_at, sr.finished_at, sr.status,
                      sr.records_seen, sr.error_count, sr.adapter_version, s.code
               FROM source_runs sr
               JOIN source_registry s ON s.id = sr.source_id
               WHERE sr.source_id = ?
                 AND sr.adapter_version = ?
                 AND sr.status != 'LOCKED'
                 AND sr.finished_at IS NOT NULL
               ORDER BY sr.started_at DESC, sr.id DESC
               LIMIT ?""",
            (
                source_id,
                adapter_version,
                limit if limit is not None else -1,
            ),
        ).fetchall()
        return [
            SourceRunRecord(
                source_code=str(row[7]),
                id=str(row[0]),
                started_at=_parse_dt(row[1]),
                finished_at=_parse_dt(row[2]) if row[2] is not None else None,
                status=str(row[3]),
                records_seen=int(row[4]),
                error_count=int(row[5]),
                adapter_version=str(row[6]),
            )
            for row in rows
        ]

    def upsert_baseline(self, baseline: SourceRunBaseline) -> None:
        source_id = self._source_id(baseline.source_code)
        self.connection.execute(
            """INSERT INTO source_run_baselines(
                 source_id, adapter_version, computed_at, sample_count,
                 median_records, mean_error_rate, mean_success_rate,
                 is_bootstrapped, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_id) DO UPDATE SET
                 adapter_version = excluded.adapter_version,
                 computed_at = excluded.computed_at,
                 sample_count = excluded.sample_count,
                 median_records = excluded.median_records,
                 mean_error_rate = excluded.mean_error_rate,
                 mean_success_rate = excluded.mean_success_rate,
                 is_bootstrapped = excluded.is_bootstrapped,
                 updated_at = excluded.updated_at""",
            (
                source_id,
                baseline.adapter_version,
                baseline.computed_at.isoformat(),
                baseline.sample_count,
                baseline.median_records,
                baseline.mean_error_rate,
                baseline.mean_success_rate,
                1 if baseline.is_bootstrapped else 0,
                _utc_now_iso(),
            ),
        )
        self.connection.commit()

    def get_baseline(self, source_code: str) -> SourceRunBaseline | None:
        source_id = self._source_id(source_code)
        row = self.connection.execute(
            """SELECT s.code, b.adapter_version, b.computed_at, b.sample_count,
                      b.median_records, b.mean_error_rate, b.mean_success_rate,
                      b.is_bootstrapped
               FROM source_run_baselines b
               JOIN source_registry s ON s.id = b.source_id
               WHERE b.source_id = ?""",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        (
            code,
            adapter_version,
            computed_at,
            sample_count,
            median_records,
            mean_error_rate,
            mean_success_rate,
            is_bootstrapped,
        ) = row
        return SourceRunBaseline(
            source_code=str(code),
            adapter_version=str(adapter_version),
            computed_at=_parse_dt(computed_at),
            sample_count=int(sample_count),
            median_records=float(median_records) if median_records is not None else None,
            mean_error_rate=float(mean_error_rate) if mean_error_rate is not None else None,
            mean_success_rate=(
                float(mean_success_rate) if mean_success_rate is not None else None
            ),
            is_bootstrapped=bool(is_bootstrapped),
        )
