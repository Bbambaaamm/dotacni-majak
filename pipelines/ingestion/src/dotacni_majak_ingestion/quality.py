from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceQualityStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


class QualityIssueCode(str, Enum):
    RECORD_COUNT_COLLAPSE = "RECORD_COUNT_COLLAPSE"
    HTTP_ERROR_RATE = "HTTP_ERROR_RATE"
    PARSE_ERROR_RATE = "PARSE_ERROR_RATE"
    VALIDATION_ERROR_RATE = "VALIDATION_ERROR_RATE"


@dataclass(frozen=True, slots=True)
class SourceRunBaseline:
    expected_records: int | None = None


@dataclass(frozen=True, slots=True)
class SourceRunMetrics:
    records_found: int
    http_requests: int = 0
    http_errors: int = 0
    parse_attempts: int = 0
    parse_errors: int = 0
    validation_attempts: int = 0
    validation_errors: int = 0


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: QualityIssueCode
    detail: str


@dataclass(frozen=True, slots=True)
class SourceQualityAssessment:
    status: SourceQualityStatus
    destructive_changes_allowed: bool
    issues: tuple[QualityIssue, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SourceQualityPolicy:
    minimum_expected_records_for_ratio_check: int = 10
    minimum_record_ratio: float = 0.25
    max_http_error_rate: float = 0.20
    max_parse_error_rate: float = 0.10
    max_validation_error_rate: float = 0.10

    def __post_init__(self) -> None:
        for name in (
            "minimum_record_ratio",
            "max_http_error_rate",
            "max_parse_error_rate",
            "max_validation_error_rate",
        ):
            value = getattr(self, name)
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1")


class SourceQualityGate:
    def __init__(self, policy: SourceQualityPolicy | None = None) -> None:
        self.policy = policy or SourceQualityPolicy()

    def assess(
        self,
        metrics: SourceRunMetrics,
        baseline: SourceRunBaseline | None = None,
    ) -> SourceQualityAssessment:
        issues: list[QualityIssue] = []

        expected = baseline.expected_records if baseline else None
        if (
            expected is not None
            and expected >= self.policy.minimum_expected_records_for_ratio_check
        ):
            ratio = metrics.records_found / expected if expected else 1.0
            if ratio < self.policy.minimum_record_ratio:
                issues.append(
                    QualityIssue(
                        QualityIssueCode.RECORD_COUNT_COLLAPSE,
                        (
                            f"records_found={metrics.records_found}, "
                            f"expected≈{expected}, ratio={ratio:.3f}"
                        ),
                    )
                )

        self._rate_issue(
            issues,
            QualityIssueCode.HTTP_ERROR_RATE,
            metrics.http_errors,
            metrics.http_requests,
            self.policy.max_http_error_rate,
        )
        self._rate_issue(
            issues,
            QualityIssueCode.PARSE_ERROR_RATE,
            metrics.parse_errors,
            metrics.parse_attempts,
            self.policy.max_parse_error_rate,
        )
        self._rate_issue(
            issues,
            QualityIssueCode.VALIDATION_ERROR_RATE,
            metrics.validation_errors,
            metrics.validation_attempts,
            self.policy.max_validation_error_rate,
        )

        degraded = bool(issues)
        return SourceQualityAssessment(
            status=(
                SourceQualityStatus.DEGRADED
                if degraded
                else SourceQualityStatus.HEALTHY
            ),
            destructive_changes_allowed=not degraded,
            issues=tuple(issues),
        )

    @staticmethod
    def _rate_issue(
        issues: list[QualityIssue],
        code: QualityIssueCode,
        failures: int,
        attempts: int,
        threshold: float,
    ) -> None:
        if attempts <= 0:
            return
        rate = failures / attempts
        if rate > threshold:
            issues.append(
                QualityIssue(
                    code,
                    f"failures={failures}, attempts={attempts}, rate={rate:.3f}",
                )
            )
