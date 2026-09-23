from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class BudgetMetric(str, Enum):
    WORKERS_REQUESTS = "WORKERS_REQUESTS"
    D1_ROWS_READ = "D1_ROWS_READ"
    D1_ROWS_WRITTEN = "D1_ROWS_WRITTEN"
    D1_STORAGE_BYTES = "D1_STORAGE_BYTES"
    R2_STORAGE_BYTES = "R2_STORAGE_BYTES"
    R2_CLASS_A_OPERATIONS = "R2_CLASS_A_OPERATIONS"
    R2_CLASS_B_OPERATIONS = "R2_CLASS_B_OPERATIONS"
    VECTOR_STORED_DIMENSIONS = "VECTOR_STORED_DIMENSIONS"
    VECTOR_QUERIED_DIMENSIONS = "VECTOR_QUERIED_DIMENSIONS"
    AI_UNITS = "AI_UNITS"
    GITHUB_ACTIONS_MINUTES = "GITHUB_ACTIONS_MINUTES"


class BudgetState(str, Enum):
    HEALTHY = "HEALTHY"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXHAUSTED = "EXHAUSTED"


class BudgetAction(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    THROTTLE = "THROTTLE"
    DEGRADE = "DEGRADE"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    hard_limit: int
    notice_threshold: float = 0.70
    warning_threshold: float = 0.85
    critical_threshold: float = 0.95
    notice_action: BudgetAction = BudgetAction.WARN
    warning_action: BudgetAction = BudgetAction.THROTTLE
    critical_action: BudgetAction = BudgetAction.DEGRADE
    exhausted_action: BudgetAction = BudgetAction.BLOCK

    def __post_init__(self) -> None:
        if self.hard_limit < 0:
            raise ValueError("hard_limit must be >= 0")
        thresholds = (
            self.notice_threshold,
            self.warning_threshold,
            self.critical_threshold,
        )
        if not all(0 <= value <= 1 for value in thresholds):
            raise ValueError("budget thresholds must be between 0 and 1")
        if not (
            self.notice_threshold
            <= self.warning_threshold
            <= self.critical_threshold
        ):
            raise ValueError("budget thresholds must be monotonic")


@dataclass(slots=True)
class BudgetUsage:
    used: int = 0

    def __post_init__(self) -> None:
        if self.used < 0:
            raise ValueError("usage must be >= 0")


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    metric: BudgetMetric
    state: BudgetState
    action: BudgetAction
    hard_limit: int
    used_before: int
    requested: int
    projected: int
    remaining_after: int
    utilization: float
    granted: bool

    @property
    def should_degrade(self) -> bool:
        return self.action in {BudgetAction.DEGRADE, BudgetAction.BLOCK}

    @property
    def should_throttle(self) -> bool:
        return self.action == BudgetAction.THROTTLE


class UnknownBudgetMetric(KeyError):
    pass


class UsageBudgetManager:
    """Provider-agnostic free-tier / quota guard.

    Limits are supplied at runtime from reviewed configuration. This module
    deliberately contains no provider pricing or free-tier constants.
    """

    def __init__(
        self,
        limits: Mapping[BudgetMetric, BudgetLimit],
        usage: Mapping[BudgetMetric, BudgetUsage] | None = None,
    ) -> None:
        if not limits:
            raise ValueError("at least one budget limit is required")
        self._limits = dict(limits)
        self._usage = {
            metric: BudgetUsage(value.used)
            for metric, value in (usage or {}).items()
        }
        for metric in self._limits:
            self._usage.setdefault(metric, BudgetUsage())

    def usage(self, metric: BudgetMetric) -> BudgetUsage:
        self._require_metric(metric)
        return BudgetUsage(self._usage[metric].used)

    def evaluate(
        self,
        metric: BudgetMetric,
        *,
        requested: int = 0,
    ) -> BudgetDecision:
        if requested < 0:
            raise ValueError("requested must be >= 0")
        limit = self._require_metric(metric)
        used = self._usage[metric].used
        projected = used + requested
        hard_limit = limit.hard_limit

        if hard_limit == 0:
            utilization = 1.0 if projected > 0 else 0.0
            exhausted = projected > 0
        else:
            utilization = projected / hard_limit
            exhausted = projected > hard_limit

        if exhausted:
            state = BudgetState.EXHAUSTED
            action = limit.exhausted_action
            granted = False
        elif utilization >= limit.critical_threshold:
            state = BudgetState.CRITICAL
            action = limit.critical_action
            granted = True
        elif utilization >= limit.warning_threshold:
            state = BudgetState.WARNING
            action = limit.warning_action
            granted = True
        elif utilization >= limit.notice_threshold:
            state = BudgetState.NOTICE
            action = limit.notice_action
            granted = True
        else:
            state = BudgetState.HEALTHY
            action = BudgetAction.ALLOW
            granted = True

        return BudgetDecision(
            metric=metric,
            state=state,
            action=action,
            hard_limit=hard_limit,
            used_before=used,
            requested=requested,
            projected=projected,
            remaining_after=max(0, hard_limit - projected),
            utilization=utilization,
            granted=granted,
        )

    def reserve(
        self,
        metric: BudgetMetric,
        amount: int,
    ) -> BudgetDecision:
        decision = self.evaluate(metric, requested=amount)
        if decision.granted:
            self._usage[metric].used = decision.projected
        return decision

    def set_usage(self, metric: BudgetMetric, used: int) -> BudgetDecision:
        if used < 0:
            raise ValueError("used must be >= 0")
        self._require_metric(metric)
        self._usage[metric].used = used
        return self.evaluate(metric)

    def snapshot(self) -> dict[BudgetMetric, BudgetDecision]:
        return {
            metric: self.evaluate(metric)
            for metric in self._limits
        }

    def _require_metric(self, metric: BudgetMetric) -> BudgetLimit:
        try:
            return self._limits[metric]
        except KeyError as exc:
            raise UnknownBudgetMetric(metric) from exc
