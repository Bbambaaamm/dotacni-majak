from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceQualityStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class SourceRunMetrics:
    records_found: int
    parse_errors: int = 0
    validation_errors: int = 0
    http_errors: int = 0
    documents_found: int = 0


@dataclass(frozen=True, slots=True)
class SourceBaseline:
    expected_records: int | None = None
    minimum_ratio: float = 0.25
    maximum_error_ratio: float = 0.20


@dataclass(frozen=True, slots=True)
class SourceQualityDecision:
    status: SourceQualityStatus
    destructive_changes_allowed: bool
    reasons: tuple[str, ...]


def evaluate_source_run(
    metrics: SourceRunMetrics,
    baseline: SourceBaseline,
) -> SourceQualityDecision:
    reasons: list[str] = []

    if metrics.records_found < 0:
        raise ValueError("records_found must be >= 0")
    if not 0 < baseline.minimum_ratio <= 1:
        raise ValueError("minimum_ratio must be within (0, 1]")
    if not 0 <= baseline.maximum_error_ratio <= 1:
        raise ValueError("maximum_error_ratio must be within [0, 1]")

    if baseline.expected_records is not None and baseline.expected_records > 0:
        ratio = metrics.records_found / baseline.expected_records
        if ratio < baseline.minimum_ratio:
            reasons.append(
                f"record_count_ratio={ratio:.3f} below minimum={baseline.minimum_ratio:.3f}"
            )

    attempted = (
        metrics.records_found
        + metrics.parse_errors
        + metrics.validation_errors
        + metrics.http_errors
    )
    errors = metrics.parse_errors + metrics.validation_errors + metrics.http_errors
    if attempted > 0 and errors / attempted > baseline.maximum_error_ratio:
        reasons.append(
            f"error_ratio={errors / attempted:.3f} above maximum={baseline.maximum_error_ratio:.3f}"
        )

    if reasons:
        return SourceQualityDecision(
            status=SourceQualityStatus.DEGRADED,
            destructive_changes_allowed=False,
            reasons=tuple(reasons),
        )

    return SourceQualityDecision(
        status=SourceQualityStatus.HEALTHY,
        destructive_changes_allowed=True,
        reasons=(),
    )
