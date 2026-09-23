from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import Iterable


class QualityStatus(str, Enum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class QualityIssueCode(str, Enum):
    RECORD_COUNT_COLLAPSE = "RECORD_COUNT_COLLAPSE"
    HIGH_HTTP_ERROR_RATE = "HIGH_HTTP_ERROR_RATE"
    LOW_PARSE_SUCCESS = "LOW_PARSE_SUCCESS"
    LOW_VALIDATION_SUCCESS = "LOW_VALIDATION_SUCCESS"


@dataclass(frozen=True, slots=True)
class SourceRunObservation:
    records_found: int
    documents_found: int = 0
    http_error_rate: float = 0.0
    parse_success_rate: float = 1.0
    validation_success_rate: float = 1.0

    def __post_init__(self) -> None:
        if self.records_found < 0 or self.documents_found < 0:
            raise ValueError("record/document counts must be non-negative")
        for name, value in (
            ("http_error_rate", self.http_error_rate),
            ("parse_success_rate", self.parse_success_rate),
            ("validation_success_rate", self.validation_success_rate),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SourceBaseline:
    records_median: float | None
    sample_count: int

    @classmethod
    def from_record_counts(cls, counts: Iterable[int]) -> "SourceBaseline":
        values = [value for value in counts if value >= 0]
        if not values:
            return cls(records_median=None, sample_count=0)
        return cls(records_median=float(median(values)), sample_count=len(values))


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: QualityIssueCode
    message: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class QualityDecision:
    status: QualityStatus
    destructive_changes_allowed: bool
    issues: tuple[QualityIssue, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    min_baseline_samples: int = 3
    blocking_record_ratio: float = 0.25
    degraded_record_ratio: float = 0.60
    max_http_error_rate: float = 0.20
    min_parse_success_rate: float = 0.90
    min_validation_success_rate: float = 0.90

    def __post_init__(self) -> None:
        if self.min_baseline_samples < 1:
            raise ValueError("min_baseline_samples must be >= 1")
        if not 0 <= self.blocking_record_ratio <= self.degraded_record_ratio <= 1:
            raise ValueError("record ratios must satisfy 0 <= blocking <= degraded <= 1")


class DataQualityGate:
    def __init__(self, thresholds: QualityThresholds | None = None) -> None:
        self.thresholds = thresholds or QualityThresholds()

    def evaluate(
        self,
        observation: SourceRunObservation,
        baseline: SourceBaseline,
    ) -> QualityDecision:
        issues: list[QualityIssue] = []

        if (
            baseline.records_median is not None
            and baseline.sample_count >= self.thresholds.min_baseline_samples
            and baseline.records_median > 0
        ):
            ratio = observation.records_found / baseline.records_median
            if ratio < self.thresholds.blocking_record_ratio:
                issues.append(
                    QualityIssue(
                        QualityIssueCode.RECORD_COUNT_COLLAPSE,
                        (
                            f"records_found={observation.records_found} is only "
                            f"{ratio:.1%} of rolling median {baseline.records_median:.1f}"
                        ),
                        True,
                    )
                )
            elif ratio < self.thresholds.degraded_record_ratio:
                issues.append(
                    QualityIssue(
                        QualityIssueCode.RECORD_COUNT_COLLAPSE,
                        (
                            f"records_found={observation.records_found} is only "
                            f"{ratio:.1%} of rolling median {baseline.records_median:.1f}"
                        ),
                        False,
                    )
                )

        if observation.http_error_rate > self.thresholds.max_http_error_rate:
            issues.append(
                QualityIssue(
                    QualityIssueCode.HIGH_HTTP_ERROR_RATE,
                    f"http_error_rate={observation.http_error_rate:.1%}",
                    True,
                )
            )

        if observation.parse_success_rate < self.thresholds.min_parse_success_rate:
            issues.append(
                QualityIssue(
                    QualityIssueCode.LOW_PARSE_SUCCESS,
                    f"parse_success_rate={observation.parse_success_rate:.1%}",
                    True,
                )
            )

        if (
            observation.validation_success_rate
            < self.thresholds.min_validation_success_rate
        ):
            issues.append(
                QualityIssue(
                    QualityIssueCode.LOW_VALIDATION_SUCCESS,
                    (
                        "validation_success_rate="
                        f"{observation.validation_success_rate:.1%}"
                    ),
                    True,
                )
            )

        if any(issue.blocking for issue in issues):
            return QualityDecision(
                status=QualityStatus.BLOCKED,
                destructive_changes_allowed=False,
                issues=tuple(issues),
            )
        if issues:
            return QualityDecision(
                status=QualityStatus.DEGRADED,
                destructive_changes_allowed=False,
                issues=tuple(issues),
            )
        return QualityDecision(
            status=QualityStatus.PASS,
            destructive_changes_allowed=True,
            issues=(),
        )
