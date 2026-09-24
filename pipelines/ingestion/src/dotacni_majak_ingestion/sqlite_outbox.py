from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .outbox import OutboxEvent, OutboxEventType, OutboxStatus


class OutboxLeaseError(RuntimeError):
    pass


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


def _row_to_event(row: tuple[object, ...]) -> OutboxEvent:
    (
        event_id,
        event_type,
        aggregate_type,
        aggregate_id,
        payload_json,
        dedupe_key,
        status,
        attempts,
        available_at,
        created_at,
        delivered_at,
        last_error,
        lease_owner,
        lease_expires_at,
        dead_lettered_at,
    ) = row
    payload = json.loads(str(payload_json))
    if not isinstance(payload, dict):
        raise ValueError("outbox payload_json must contain an object")
    return OutboxEvent(
        id=str(event_id),
        event_type=OutboxEventType(str(event_type)),
        aggregate_type=str(aggregate_type),
        aggregate_id=str(aggregate_id),
        payload=payload,
        dedupe_key=str(dedupe_key),
        status=OutboxStatus(str(status)),
        attempts=int(attempts),
        available_at=str(available_at),
        created_at=str(created_at),
        delivered_at=str(delivered_at) if delivered_at is not None else None,
        last_error=str(last_error) if last_error is not None else None,
        lease_owner=str(lease_owner) if lease_owner is not None else None,
        lease_expires_at=(
            str(lease_expires_at) if lease_expires_at is not None else None
        ),
        dead_lettered_at=(
            str(dead_lettered_at) if dead_lettered_at is not None else None
        ),
    )


_SELECT_COLUMNS = """
  id,event_type,aggregate_type,aggregate_id,payload_json,dedupe_key,
  status,attempts,available_at,created_at,delivered_at,last_error,
  lease_owner,lease_expires_at,dead_lettered_at
"""


class SqliteOutboxRepository:
    """Transactional outbox reference repository with D1-compatible SQL."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")

    def enqueue(
        self,
        *,
        event_type: OutboxEventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        dedupe_key: str,
        now: datetime | None = None,
        commit: bool = True,
    ) -> OutboxEvent:
        if not aggregate_type.strip() or not aggregate_id.strip():
            raise ValueError("aggregate_type and aggregate_id must not be empty")
        if not dedupe_key.strip():
            raise ValueError("dedupe_key must not be empty")

        created = _utc(now)
        event_id = uuid4().hex
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.connection.execute(
            """INSERT OR IGNORE INTO outbox_events(
                 id,event_type,aggregate_type,aggregate_id,payload_json,
                 dedupe_key,status,attempts,available_at,created_at
               ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)""",
            (
                event_id,
                event_type.value,
                aggregate_type,
                aggregate_id,
                payload_json,
                dedupe_key,
                created.isoformat(),
                created.isoformat(),
            ),
        )
        if commit:
            self.connection.commit()

        event = self.get_by_dedupe_key(dedupe_key)
        if event is None:
            raise RuntimeError("outbox enqueue did not persist or find event")
        return event

    def get(self, event_id: str) -> OutboxEvent | None:
        row = self.connection.execute(
            f"""SELECT {_SELECT_COLUMNS}
                FROM outbox_events WHERE id = ?""",
            (event_id,),
        ).fetchone()
        return _row_to_event(row) if row else None

    def get_by_dedupe_key(self, dedupe_key: str) -> OutboxEvent | None:
        row = self.connection.execute(
            f"""SELECT {_SELECT_COLUMNS}
                FROM outbox_events WHERE dedupe_key = ?""",
            (dedupe_key,),
        ).fetchone()
        return _row_to_event(row) if row else None

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
        lease_seconds: int = 60,
    ) -> OutboxEvent | None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")

        current = _utc(now)
        now_iso = current.isoformat()
        lease_until = (current + timedelta(seconds=lease_seconds)).isoformat()

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                f"""SELECT {_SELECT_COLUMNS}
                    FROM outbox_events
                    WHERE dead_lettered_at IS NULL
                      AND (
                        (
                          status IN ('PENDING','FAILED')
                          AND available_at <= ?
                        )
                        OR (
                          status = 'PROCESSING'
                          AND lease_expires_at IS NOT NULL
                          AND lease_expires_at <= ?
                        )
                      )
                    ORDER BY available_at ASC, created_at ASC, id ASC
                    LIMIT 1""",
                (now_iso, now_iso),
            ).fetchone()
            if row is None:
                self.connection.commit()
                return None

            event = _row_to_event(row)
            result = self.connection.execute(
                """UPDATE outbox_events
                   SET status = 'PROCESSING',
                       attempts = attempts + 1,
                       lease_owner = ?,
                       lease_expires_at = ?,
                       last_error = NULL
                   WHERE id = ?
                     AND dead_lettered_at IS NULL""",
                (worker_id, lease_until, event.id),
            )
            if result.rowcount != 1:
                self.connection.rollback()
                return None

            self.connection.commit()
            claimed = self.get(event.id)
            if claimed is None:
                raise RuntimeError("claimed outbox event disappeared")
            return claimed
        except Exception:
            self.connection.rollback()
            raise

    def mark_delivered(
        self,
        event_id: str,
        *,
        worker_id: str,
        now: datetime | None = None,
    ) -> OutboxEvent:
        delivered = _utc(now)
        result = self.connection.execute(
            """UPDATE outbox_events
               SET status = 'DELIVERED',
                   delivered_at = ?,
                   last_error = NULL,
                   lease_owner = NULL,
                   lease_expires_at = NULL
               WHERE id = ?
                 AND status = 'PROCESSING'
                 AND lease_owner = ?
                 AND dead_lettered_at IS NULL""",
            (delivered.isoformat(), event_id, worker_id),
        )
        if result.rowcount != 1:
            self.connection.rollback()
            raise OutboxLeaseError(
                "cannot deliver event without the active worker lease"
            )
        self.connection.commit()
        event = self.get(event_id)
        if event is None:
            raise RuntimeError("delivered outbox event disappeared")
        return event

    def mark_failed(
        self,
        event_id: str,
        *,
        worker_id: str,
        error: Exception,
        now: datetime | None = None,
        max_attempts: int = 5,
        retry_after_seconds: int = 30,
    ) -> OutboxEvent:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be >= 0")

        current = _utc(now)
        event = self.get(event_id)
        if (
            event is None
            or event.status != OutboxStatus.PROCESSING
            or event.lease_owner != worker_id
        ):
            raise OutboxLeaseError(
                "cannot fail event without the active worker lease"
            )

        is_dead_letter = event.attempts >= max_attempts
        available_at = (
            current
            if is_dead_letter
            else current + timedelta(seconds=retry_after_seconds)
        )
        dead_lettered_at = current.isoformat() if is_dead_letter else None
        message = f"{type(error).__name__}: {error}"

        result = self.connection.execute(
            """UPDATE outbox_events
               SET status = 'FAILED',
                   available_at = ?,
                   last_error = ?,
                   lease_owner = NULL,
                   lease_expires_at = NULL,
                   dead_lettered_at = ?
               WHERE id = ?
                 AND status = 'PROCESSING'
                 AND lease_owner = ?""",
            (
                available_at.isoformat(),
                message,
                dead_lettered_at,
                event_id,
                worker_id,
            ),
        )
        if result.rowcount != 1:
            self.connection.rollback()
            raise OutboxLeaseError(
                "outbox event lease changed during failure update"
            )
        self.connection.commit()

        updated = self.get(event_id)
        if updated is None:
            raise RuntimeError("failed outbox event disappeared")
        return updated

    def metrics(self, *, now: datetime | None = None) -> dict[str, int]:
        current = _utc(now).isoformat()
        rows = self.connection.execute(
            """SELECT status, COUNT(*)
               FROM outbox_events
               GROUP BY status"""
        ).fetchall()
        counts = {str(status): int(count) for status, count in rows}
        dead_letter = self.connection.execute(
            """SELECT COUNT(*) FROM outbox_events
               WHERE dead_lettered_at IS NOT NULL"""
        ).fetchone()[0]
        ready = self.connection.execute(
            """SELECT COUNT(*) FROM outbox_events
               WHERE dead_lettered_at IS NULL
                 AND status IN ('PENDING','FAILED')
                 AND available_at <= ?""",
            (current,),
        ).fetchone()[0]
        return {
            "pending": counts.get("PENDING", 0),
            "processing": counts.get("PROCESSING", 0),
            "failed": counts.get("FAILED", 0),
            "delivered": counts.get("DELIVERED", 0),
            "dead_letter": int(dead_letter),
            "ready": int(ready),
        }
