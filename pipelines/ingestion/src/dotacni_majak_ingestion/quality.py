from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Iterable


class SourceRunQuality(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class SourceRunMetrics:
    records_found: int
    http_error_rate: float = 0.0
    parse_error_rate: float = 0.0
    validation_error_rate: float = 0.0
    documents_found: int = 0


@dataclass(frozen=True, slots=True)
class QualityDecision:
    status: SourceRunQuality
    destructive_changes_allowed: bool
    reasons: tuple[str, ...] = ()


class SourceRunQualityGate:
    """Conservative run-level anomaly detector.

    A degraded run must never trigger destructive canonical changes.
    Thresholds are intentionally simple and deterministic for v1.
    """

    def __init__(
        self,
        *,
        minimum_history: int = 3,
        record_floor_ratio: float = 0.25,
        max_http_error_rate: float = 0.25,
        max_parse_error_rate: float = 0.20,
        max_validation_error_rate: float = 0.20,
    ) -> None:
        self.minimum_history = minimum_history
        self.record_floor_ratio = record_floor_ratio
        self.max_http_error_rate = max_http_error_rate
        self.max_parse_error_rate = max_parse_error_rate
        self.max_validation_error_rate = max_validation_error_rate

    def evaluate(
        self,
        current: SourceRunMetrics,
        history: Iterable[SourceRunMetrics],
    ) -> QualityDecision:
        reasons: list[str] = []
        history = list(history)

        if current.http_error_rate > self.max_http_error_rate:
            reasons.append("http_error_rate")
        if current.parse_error_rate > self.max_parse_error_rate:
            reasons.append("parse_error_rate")
        if current.validation_error_rate > self.max_validation_error_rate:
            reasons.append("validation_error_rate")

        if len(history) >= self.minimum_history:
            baseline = median(x.records_found for x in history[-10:])
            if baseline > 0 and current.records_found < baseline * self.record_floor_ratio:
                reasons.append("records_found_anomaly")

        status = SourceRunQuality.DEGRADED if reasons else SourceRunQuality.HEALTHY
        return QualityDecision(
            status=status,
            destructive_changes_allowed=status == SourceRunQuality.HEALTHY,
            reasons=tuple(reasons),
        )
