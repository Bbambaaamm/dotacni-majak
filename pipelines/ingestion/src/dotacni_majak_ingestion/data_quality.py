from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QualityGateStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class QualityGateConfig:
    min_baseline_samples: int = 3
    min_records_ratio: float = 0.35
    max_http_error_rate: float = 0.20
    min_parse_success_rate: float = 0.85
    min_validation_success_rate: float = 0.85

    def __post_init__(self) -> None:
        if self.min_baseline_samples < 1:
            raise ValueError("min_baseline_samples must be >= 1")
        for value, name in (
            (self.min_records_ratio, "min_records_ratio"),
            (self.max_http_error_rate, "max_http_error_rate"),
            (self.min_parse_success_rate, "min_parse_success_rate"),
            (self.min_validation_success_rate, "min_validation_success_rate"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SourceRunObservation:
    records_found: int
    baseline_samples: int = 0
    baseline_median_records: float | None = None
    http_requests: int = 0
    http_errors: int = 0
    parse_attempts: int = 0
    parse_failures: int = 0
    validation_attempts: int = 0
    validation_failures: int = 0
    unexpected_structure_change: bool = False

    def __post_init__(self) -> None:
        numeric = {
            "records_found": self.records_found,
            "baseline_samples": self.baseline_samples,
            "http_requests": self.http_requests,
            "http_errors": self.http_errors,
            "parse_attempts": self.parse_attempts,
            "parse_failures": self.parse_failures,
            "validation_attempts": self.validation_attempts,
            "validation_failures": self.validation_failures,
        }
        for name, value in numeric.items():
            if value < 0:
                raise ValueError(f"{name} must be >= 0")
        if self.http_errors > self.http_requests:
            raise ValueError("http_errors cannot exceed http_requests")
        if self.parse_failures > self.parse_attempts:
            raise ValueError("parse_failures cannot exceed parse_attempts")
        if self.validation_failures > self.validation_attempts:
            raise ValueError(
                "validation_failures cannot exceed validation_attempts"
            )
        if (
            self.baseline_median_records is not None
            and self.baseline_median_records < 0
        ):
            raise ValueError("baseline_median_records must be >= 0")


@dataclass(frozen=True, slots=True)
class QualityViolation:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class QualityGateDecision:
    status: QualityGateStatus
    destructive_changes_allowed: bool
    violations: tuple[QualityViolation, ...]

    @property
    def is_degraded(self) -> bool:
        return self.status == QualityGateStatus.DEGRADED


class SourceRunQualityGate:
    """Detects suspicious source runs before destructive publication.

    A degraded run may still contribute newly discovered/non-destructive data,
    but it must never be used to mass-close, cancel or delete last-known-good
    canonical records.
    """

    def __init__(self, config: QualityGateConfig | None = None) -> None:
        self.config = config or QualityGateConfig()

    def evaluate(self, observation: SourceRunObservation) -> QualityGateDecision:
        violations: list[QualityViolation] = []

        if observation.unexpected_structure_change:
            violations.append(
                QualityViolation(
                    code="UNEXPECTED_STRUCTURE_CHANGE",
                    message="Source structure changed unexpectedly.",
                )
            )

        if (
            observation.baseline_samples >= self.config.min_baseline_samples
            and observation.baseline_median_records is not None
            and observation.baseline_median_records > 0
        ):
            ratio = (
                observation.records_found
                / observation.baseline_median_records
            )
            if ratio < self.config.min_records_ratio:
                violations.append(
                    QualityViolation(
                        code="RECORD_COUNT_COLLAPSE",
                        message=(
                            "Record count is far below the rolling baseline: "
                            f"{observation.records_found} vs median "
                            f"{observation.baseline_median_records:g}."
                        ),
                    )
                )

        http_error_rate = self._failure_rate(
            observation.http_errors,
            observation.http_requests,
        )
        if (
            http_error_rate is not None
            and http_error_rate > self.config.max_http_error_rate
        ):
            violations.append(
                QualityViolation(
                    code="HTTP_ERROR_RATE_HIGH",
                    message=f"HTTP error rate is {http_error_rate:.1%}.",
                )
            )

        parse_success = self._success_rate(
            observation.parse_failures,
            observation.parse_attempts,
        )
        if (
            parse_success is not None
            and parse_success < self.config.min_parse_success_rate
        ):
            violations.append(
                QualityViolation(
                    code="PARSE_SUCCESS_LOW",
                    message=f"Parse success rate is {parse_success:.1%}.",
                )
            )

        validation_success = self._success_rate(
            observation.validation_failures,
            observation.validation_attempts,
        )
        if (
            validation_success is not None
            and validation_success
            < self.config.min_validation_success_rate
        ):
            violations.append(
                QualityViolation(
                    code="VALIDATION_SUCCESS_LOW",
                    message=(
                        "Validation success rate is "
                        f"{validation_success:.1%}."
                    ),
                )
            )

        if violations:
            return QualityGateDecision(
                status=QualityGateStatus.DEGRADED,
                destructive_changes_allowed=False,
                violations=tuple(violations),
            )

        return QualityGateDecision(
            status=QualityGateStatus.HEALTHY,
            destructive_changes_allowed=True,
            violations=(),
        )

    @staticmethod
    def _failure_rate(failures: int, attempts: int) -> float | None:
        if attempts == 0:
            return None
        return failures / attempts

    @staticmethod
    def _success_rate(failures: int, attempts: int) -> float | None:
        if attempts == 0:
            return None
        return 1.0 - (failures / attempts)
