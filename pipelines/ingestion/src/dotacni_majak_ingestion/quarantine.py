from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class QuarantineReason(str, Enum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    QUALITY_GATE = "QUALITY_GATE"
    DUPLICATE_AMBIGUOUS = "DUPLICATE_AMBIGUOUS"
    SECURITY_REJECTED = "SECURITY_REJECTED"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class QuarantineItem:
    id: str
    source_code: str
    reason: QuarantineReason
    created_at: str
    external_id: str | None = None
    details: str | None = None
    payload_ref: str | None = None
    resolved_at: str | None = None
    resolution_note: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


class InMemoryQuarantineRepository:
    def __init__(self) -> None:
        self._items: dict[str, QuarantineItem] = {}

    def add(
        self,
        *,
        source_code: str,
        reason: QuarantineReason,
        external_id: str | None = None,
        details: str | None = None,
        payload_ref: str | None = None,
        now: datetime | None = None,
    ) -> QuarantineItem:
        created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        item = QuarantineItem(
            id=uuid4().hex,
            source_code=source_code,
            reason=reason,
            external_id=external_id,
            details=details,
            payload_ref=payload_ref,
            created_at=created.isoformat(),
        )
        self._items[item.id] = item
        return item

    def unresolved(self, *, source_code: str | None = None) -> list[QuarantineItem]:
        items = [
            item
            for item in self._items.values()
            if not item.is_resolved
            and (source_code is None or item.source_code == source_code)
        ]
        return sorted(items, key=lambda item: item.created_at)

    def resolve(
        self,
        item_id: str,
        *,
        note: str,
        now: datetime | None = None,
    ) -> QuarantineItem:
        item = self._items[item_id]
        if item.is_resolved:
            return item
        resolved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        updated = replace(
            item,
            resolved_at=resolved.isoformat(),
            resolution_note=note,
        )
        self._items[item_id] = updated
        return updated
