from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .quarantine import QuarantineItem
from .sqlite_quarantine import SqliteQuarantineRepository


ReprocessHandler = Callable[[QuarantineItem], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class ReprocessResult:
    quarantine_item_id: str
    attempt_id: str
    status: str
    error: str | None = None


class QuarantineReprocessor:
    """Explicit reprocess service for already quarantined RAW payloads.

    Failure leaves the quarantine item unresolved. Success resolves it only after
    the handler completes, preserving a complete audit trail.
    """

    def __init__(
        self,
        *,
        repository: SqliteQuarantineRepository,
        handler: ReprocessHandler,
        requested_by: str,
        parser_version: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not requested_by.strip():
            raise ValueError("requested_by must not be empty")
        self.repository = repository
        self.handler = handler
        self.requested_by = requested_by
        self.parser_version = parser_version
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    async def reprocess(self, quarantine_item_id: str) -> ReprocessResult:
        item = self.repository.get(quarantine_item_id)
        if item is None:
            raise KeyError(quarantine_item_id)
        if item.is_resolved:
            raise ValueError("resolved quarantine item cannot be reprocessed")
        if not item.payload_ref:
            raise ValueError("quarantine item has no RAW payload_ref")

        attempt_id = self.repository.create_reprocess_attempt(
            quarantine_item_id=item.id,
            requested_by=self.requested_by,
            parser_version=self.parser_version,
            now=self._now(),
        )
        self.repository.mark_reprocess_running(attempt_id, now=self._now())

        try:
            result = self.handler(item)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            self.repository.finish_reprocess(
                attempt_id,
                succeeded=False,
                error=exc,
                now=self._now(),
            )
            return ReprocessResult(
                quarantine_item_id=item.id,
                attempt_id=attempt_id,
                status="FAILED",
                error=f"{type(exc).__name__}: {exc}",
            )

        self.repository.finish_reprocess(
            attempt_id,
            succeeded=True,
            now=self._now(),
        )
        self.repository.resolve(
            item.id,
            note=f"reprocessed successfully via attempt {attempt_id}",
            now=self._now(),
        )
        return ReprocessResult(
            quarantine_item_id=item.id,
            attempt_id=attempt_id,
            status="SUCCEEDED",
        )
