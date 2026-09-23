from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from .data_quality import QualityGateStatus


class SourceHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class HealthReason(str, Enum):
    QUALITY_GATE_DEGRADED = "QUALITY_GATE_DEGRADED"
    DIRECT_HEALTHCHECK_UNAVAILABLE = "DIRECT_HEALTHCHECK_UNAVAILABLE"
    SCHEDULED_RUN_MISSED = "SCHEDULED_RUN_MISSED"
    LAST_SUCCESS_STALE = "LAST_SUCCESS_STALE"
    NEVER_RUN = "NEVER_RUN"
    NEVER_SUCCEEDED = "NEVER_SUCCEEDED"


@dataclass(frozen=True, slots=True)
class ScheduleHealthInput:
    expected_interval: timedelta
    last_expected_run_at: datetime | None
    last_actual_run_at: datetime | None
    last_success_at: datetime | None
    grace_period: timedelta = timedelta(minutes=15)
    unavailable_after_intervals: int = 3

    def __post_init__(self) -> None:
        if self.expected_interval <= timedelta(0):
            raise ValueError("expected_interval must be positive")
        if self.grace_period < timedelta(0):
            raise ValueError("grace_period must be >= 0")
        if self.unavailable_after_intervals < 1:
            raise ValueError("unavailable_after_intervals must be >= 1")


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshot:
    source_code: str
    status: SourceHealthStatus
    reasons: tuple[HealthReason, ...]
    last_checked_at: datetime
    last_expected_run_at: datetime | None
    last_actual_run_at: datetime | None
    last_success_at: datetime | None
    last_change_at: datetime | None
    records_found: int | None
    documents_found: int | None
    adapter_version: str | None

    @property
    def serves_last_known_good(self) -> bool:
        return self.status is not SourceHealthStatus.HEALTHY


class SourceHealthEvaluator:
    def evaluate(
        self,
        *,
        source_code: str,
        now: datetime,
        schedule: ScheduleHealthInput,
        quality_status: QualityGateStatus | None,
        direct_healthcheck_available: bool = True,
        last_change_at: datetime | None = None,
        records_found: int | None = None,
        documents_found: int | None = None,
        adapter_version: str | None = None,
    ) -> SourceHealthSnapshot:
        now = _utc(now)
        reasons: list[HealthReason] = []

        if not direct_healthcheck_available:
            reasons.append(HealthReason.DIRECT_HEALTHCHECK_UNAVAILABLE)

        if schedule.last_actual_run_at is None:
            reasons.append(HealthReason.NEVER_RUN)
        if (
            schedule.last_actual_run_at is not None
            and schedule.last_success_at is None
        ):
            reasons.append(HealthReason.NEVER_SUCCEEDED)

        if self._missed_run(now, schedule):
            reasons.append(HealthReason.SCHEDULED_RUN_MISSED)

        if self._stale_success(now, schedule):
            reasons.append(HealthReason.LAST_SUCCESS_STALE)

        if quality_status is QualityGateStatus.DEGRADED:
            reasons.append(HealthReason.QUALITY_GATE_DEGRADED)

        status = self._status(reasons)

        return SourceHealthSnapshot(
            source_code=source_code,
            status=status,
            reasons=tuple(dict.fromkeys(reasons)),
            last_checked_at=now,
            last_expected_run_at=_maybe_utc(schedule.last_expected_run_at),
            last_actual_run_at=_maybe_utc(schedule.last_actual_run_at),
            last_success_at=_maybe_utc(schedule.last_success_at),
            last_change_at=_maybe_utc(last_change_at),
            records_found=records_found,
            documents_found=documents_found,
            adapter_version=adapter_version,
        )

    @staticmethod
    def _missed_run(now: datetime, schedule: ScheduleHealthInput) -> bool:
        expected = schedule.last_expected_run_at
        if expected is None:
            return False

        expected = _utc(expected)
        actual = _maybe_utc(schedule.last_actual_run_at)

        if now <= expected + schedule.grace_period:
            return False

        if actual is None:
            return True

        # The most recent actual run must correspond to or follow the most
        # recent expected slot; an older run does not satisfy this schedule.
        return actual < expected

    @staticmethod
    def _stale_success(now: datetime, schedule: ScheduleHealthInput) -> bool:
        success = schedule.last_success_at
        if success is None:
            return schedule.last_actual_run_at is not None

        max_age = (
            schedule.expected_interval
            * schedule.unavailable_after_intervals
            + schedule.grace_period
        )
        return now - _utc(success) > max_age

    @staticmethod
    def _status(reasons: list[HealthReason]) -> SourceHealthStatus:
        hard = {
            HealthReason.DIRECT_HEALTHCHECK_UNAVAILABLE,
            HealthReason.LAST_SUCCESS_STALE,
            HealthReason.NEVER_SUCCEEDED,
        }
        if any(reason in hard for reason in reasons):
            return SourceHealthStatus.UNAVAILABLE
        if reasons:
            return SourceHealthStatus.DEGRADED
        return SourceHealthStatus.HEALTHY


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("health timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _maybe_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)
