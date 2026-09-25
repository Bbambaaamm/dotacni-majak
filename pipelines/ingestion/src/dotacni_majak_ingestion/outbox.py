from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class OutboxEventType(str, Enum):
    SEARCH_REINDEX_REQUIRED = "SEARCH_REINDEX_REQUIRED"
    VECTOR_REINDEX_REQUIRED = "VECTOR_REINDEX_REQUIRED"
    CHANGE_DETECTION_REQUIRED = "CHANGE_DETECTION_REQUIRED"
    WATCH_REEVALUATION_REQUIRED = "WATCH_REEVALUATION_REQUIRED"
    NOTIFICATION_REQUIRED = "NOTIFICATION_REQUIRED"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: str
    event_type: OutboxEventType
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any]
    dedupe_key: str
    status: OutboxStatus
    attempts: int
    available_at: str
    created_at: str
    delivered_at: str | None = None
    last_error: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    dead_lettered_at: str | None = None


class InMemoryOutboxRepository:
    """Reference implementation of idempotent transactional-outbox semantics.

    Production D1 code must enqueue the canonical write and its outbox event in
    the same database transaction. The UNIQUE(dedupe_key) DB constraint is the
    final idempotency guard.
    """

    def __init__(self) -> None:
        self._events: dict[str, OutboxEvent] = {}
        self._by_dedupe: dict[str, str] = {}

    def enqueue(
        self,
        *,
        event_type: OutboxEventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        dedupe_key: str,
        now: datetime | None = None,
    ) -> OutboxEvent:
        existing_id = self._by_dedupe.get(dedupe_key)
        if existing_id is not None:
            return self._events[existing_id]

        created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        event = OutboxEvent(
            id=uuid4().hex,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=dict(payload),
            dedupe_key=dedupe_key,
            status=OutboxStatus.PENDING,
            attempts=0,
            available_at=created.isoformat(),
            created_at=created.isoformat(),
        )
        self._events[event.id] = event
        self._by_dedupe[dedupe_key] = event.id
        return event

    def pending(self) -> list[OutboxEvent]:
        return [
            event
            for event in self._events.values()
            if event.status in {OutboxStatus.PENDING, OutboxStatus.FAILED}
        ]

    def claim(self, event_id: str) -> OutboxEvent:
        event = self._events[event_id]
        if event.status == OutboxStatus.DELIVERED:
            return event
        updated = replace(
            event,
            status=OutboxStatus.PROCESSING,
            attempts=event.attempts + 1,
            last_error=None,
        )
        self._events[event_id] = updated
        return updated

    def mark_delivered(
        self,
        event_id: str,
        *,
        now: datetime | None = None,
    ) -> OutboxEvent:
        event = self._events[event_id]
        delivered = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        updated = replace(
            event,
            status=OutboxStatus.DELIVERED,
            delivered_at=delivered.isoformat(),
            last_error=None,
        )
        self._events[event_id] = updated
        return updated

    def mark_failed(self, event_id: str, error: Exception) -> OutboxEvent:
        event = self._events[event_id]
        updated = replace(
            event,
            status=OutboxStatus.FAILED,
            last_error=f"{type(error).__name__}: {error}",
        )
        self._events[event_id] = updated
        return updated
