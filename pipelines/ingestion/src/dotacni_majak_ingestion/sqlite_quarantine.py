from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from .quarantine import QuarantineItem, QuarantineReason


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


class SqliteQuarantineRepository:
    """Persistent quarantine queue linked to Source Registry and RAW refs."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")

    def _source_id(self, source_code: str) -> str:
        row = self.connection.execute(
            "SELECT id FROM source_registry WHERE code = ?",
            (source_code,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown source_code {source_code!r}")
        return str(row[0])

    def _row_to_item(self, row: tuple[object, ...]) -> QuarantineItem:
        (
            item_id,
            source_code,
            reason,
            external_id,
            details_json,
            payload_ref,
            created_at,
            resolved_at,
            resolution_note,
        ) = row
        details = None
        if details_json:
            loaded = json.loads(str(details_json))
            if isinstance(loaded, dict):
                details = str(loaded.get("message")) if loaded.get("message") is not None else None
            elif loaded is not None:
                details = str(loaded)
        return QuarantineItem(
            id=str(item_id),
            source_code=str(source_code),
            reason=QuarantineReason(str(reason)),
            created_at=str(created_at),
            external_id=(str(external_id) if external_id is not None else None),
            details=details,
            payload_ref=(str(payload_ref) if payload_ref is not None else None),
            resolved_at=(str(resolved_at) if resolved_at is not None else None),
            resolution_note=(str(resolution_note) if resolution_note is not None else None),
        )

    def get(self, item_id: str) -> QuarantineItem | None:
        row = self.connection.execute(
            """SELECT q.id, s.code, q.reason, q.external_id, q.details_json,
                      q.payload_ref, q.created_at, q.resolved_at, q.resolution_note
               FROM quarantine_items q
               JOIN source_registry s ON s.id = q.source_id
               WHERE q.id = ?""",
            (item_id,),
        ).fetchone()
        return self._row_to_item(row) if row else None

    def add(
        self,
        *,
        source_code: str,
        reason: QuarantineReason,
        external_id: str | None = None,
        details: str | None = None,
        payload_ref: str | None = None,
        source_run_id: str | None = None,
        now: datetime | None = None,
    ) -> QuarantineItem:
        source_id = self._source_id(source_code)
        created = _utc(now).isoformat()
        item_id = uuid4().hex
        details_json = (
            json.dumps({"message": details}, ensure_ascii=False, sort_keys=True)
            if details is not None
            else None
        )
        self.connection.execute(
            """INSERT INTO quarantine_items(
                 id, source_id, source_run_id, external_id, reason,
                 details_json, payload_ref, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                source_id,
                source_run_id,
                external_id,
                reason.value,
                details_json,
                payload_ref,
                created,
            ),
        )
        self.connection.commit()
        item = self.get(item_id)
        if item is None:
            raise RuntimeError("quarantine item was not persisted")
        return item

    def unresolved(
        self,
        *,
        source_code: str | None = None,
        limit: int = 100,
    ) -> list[QuarantineItem]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        params: list[object] = []
        where = "q.resolved_at IS NULL"
        if source_code is not None:
            where += " AND s.code = ?"
            params.append(source_code)
        params.append(limit)
        rows = self.connection.execute(
            f"""SELECT q.id, s.code, q.reason, q.external_id, q.details_json,
                       q.payload_ref, q.created_at, q.resolved_at, q.resolution_note
                FROM quarantine_items q
                JOIN source_registry s ON s.id = q.source_id
                WHERE {where}
                ORDER BY q.created_at ASC, q.id ASC
                LIMIT ?""",
            tuple(params),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def resolve(
        self,
        item_id: str,
        *,
        note: str,
        now: datetime | None = None,
    ) -> QuarantineItem:
        if not note.strip():
            raise ValueError("resolution note must not be empty")
        current = _utc(now).isoformat()
        self.connection.execute(
            """UPDATE quarantine_items
               SET resolved_at = COALESCE(resolved_at, ?),
                   resolution_note = COALESCE(resolution_note, ?)
               WHERE id = ?""",
            (current, note, item_id),
        )
        self.connection.commit()
        item = self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def create_reprocess_attempt(
        self,
        *,
        quarantine_item_id: str,
        requested_by: str,
        parser_version: str | None,
        now: datetime | None = None,
    ) -> str:
        if not requested_by.strip():
            raise ValueError("requested_by must not be empty")
        if self.get(quarantine_item_id) is None:
            raise KeyError(quarantine_item_id)
        attempt_id = uuid4().hex
        self.connection.execute(
            """INSERT INTO quarantine_reprocess_attempts(
                 id, quarantine_item_id, parser_version, requested_by,
                 status, requested_at
               ) VALUES (?, ?, ?, ?, 'REQUESTED', ?)""",
            (
                attempt_id,
                quarantine_item_id,
                parser_version,
                requested_by,
                _utc(now).isoformat(),
            ),
        )
        self.connection.commit()
        return attempt_id

    def mark_reprocess_running(
        self,
        attempt_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        result = self.connection.execute(
            """UPDATE quarantine_reprocess_attempts
               SET status='RUNNING', started_at=?
               WHERE id=? AND status='REQUESTED'""",
            (_utc(now).isoformat(), attempt_id),
        )
        if result.rowcount != 1:
            raise RuntimeError("reprocess attempt is not REQUESTED")
        self.connection.commit()

    def finish_reprocess(
        self,
        attempt_id: str,
        *,
        succeeded: bool,
        error: Exception | None = None,
        now: datetime | None = None,
    ) -> None:
        status = "SUCCEEDED" if succeeded else "FAILED"
        message = None if error is None else f"{type(error).__name__}: {error}"
        result = self.connection.execute(
            """UPDATE quarantine_reprocess_attempts
               SET status=?, finished_at=?, last_error=?
               WHERE id=? AND status='RUNNING'""",
            (status, _utc(now).isoformat(), message, attempt_id),
        )
        if result.rowcount != 1:
            raise RuntimeError("reprocess attempt is not RUNNING")
        self.connection.commit()

    def reprocess_attempts(self, quarantine_item_id: str) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """SELECT id, parser_version, requested_by, status,
                      requested_at, started_at, finished_at, last_error
               FROM quarantine_reprocess_attempts
               WHERE quarantine_item_id=?
               ORDER BY requested_at ASC, id ASC""",
            (quarantine_item_id,),
        ).fetchall()
        keys = (
            "id", "parser_version", "requested_by", "status",
            "requested_at", "started_at", "finished_at", "last_error",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]
