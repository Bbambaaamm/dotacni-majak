from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from .outbox import OutboxEvent, OutboxEventType
from .sqlite_outbox import SqliteOutboxRepository


OutboxHandler = Callable[[OutboxEvent], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: int = 30
    max_delay_seconds: int = 60 * 60

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be >= 0")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_delay_seconds must be >= base_delay_seconds"
            )

    def delay_for_attempt(self, attempt: int) -> int:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        delay = self.base_delay_seconds * (2 ** (attempt - 1))
        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True, slots=True)
class OutboxWorkerResult:
    event_id: str | None
    status: str
    attempts: int = 0
    error: str | None = None


class OutboxWorker:
    """At-least-once outbox consumer with lease/retry/dead-letter semantics."""

    def __init__(
        self,
        *,
        repository: SqliteOutboxRepository,
        handlers: Mapping[OutboxEventType, OutboxHandler],
        worker_id: str,
        retry_policy: RetryPolicy | None = None,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        self.repository = repository
        self.handlers = dict(handlers)
        self.worker_id = worker_id
        self.retry_policy = retry_policy or RetryPolicy()
        self.lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("worker clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    async def run_once(self) -> OutboxWorkerResult:
        event = self.repository.claim_next(
            worker_id=self.worker_id,
            now=self._now(),
            lease_seconds=self.lease_seconds,
        )
        if event is None:
            return OutboxWorkerResult(event_id=None, status="IDLE")

        handler = self.handlers.get(event.event_type)
        if handler is None:
            return self._fail(
                event,
                RuntimeError(
                    f"no handler registered for {event.event_type.value}"
                ),
            )

        try:
            result = handler(event)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            return self._fail(event, exc)

        delivered = self.repository.mark_delivered(
            event.id,
            worker_id=self.worker_id,
            now=self._now(),
        )
        return OutboxWorkerResult(
            event_id=event.id,
            status="DELIVERED",
            attempts=delivered.attempts,
        )

    def _fail(
        self,
        event: OutboxEvent,
        error: Exception,
    ) -> OutboxWorkerResult:
        failed = self.repository.mark_failed(
            event.id,
            worker_id=self.worker_id,
            error=error,
            now=self._now(),
            max_attempts=self.retry_policy.max_attempts,
            retry_after_seconds=self.retry_policy.delay_for_attempt(
                event.attempts
            ),
        )
        return OutboxWorkerResult(
            event_id=event.id,
            status=(
                "DEAD_LETTER"
                if failed.dead_lettered_at
                else "RETRY_SCHEDULED"
            ),
            attempts=failed.attempts,
            error=failed.last_error,
        )
