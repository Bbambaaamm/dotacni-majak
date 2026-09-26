from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


class SourceRecordChange(str, Enum):
    NEW = "NEW"
    CHANGED = "CHANGED"
    NOT_MODIFIED = "NOT_MODIFIED"


@dataclass(frozen=True, slots=True)
class SourceRecordObservation:
    record_id: str
    source_code: str
    external_id: str
    canonical_url: str
    record_type: str
    content_hash: str
    change: SourceRecordChange
    first_seen_at: str
    last_seen_at: str
    presence_state: str
    missing_run_count: int
    grant_call_id: str | None
    previous_content_hash: str | None = None


class SqliteSourceRecordRepository:
    """Observe stable upstream identities before expensive parse/publish work."""

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

    @staticmethod
    def _validate_hash(content_hash: str) -> None:
        if not _HASH_RE.fullmatch(content_hash):
            raise ValueError("content_hash must be lowercase SHA-256 hex")

    def _get_by_identity(
        self,
        source_id: str,
        external_id: str,
    ) -> tuple[object, ...] | None:
        return self.connection.execute(
            """SELECT
                 id, canonical_url, record_type, content_hash,
                 first_seen_at, last_seen_at, presence_state,
                 missing_run_count, grant_call_id
               FROM source_records
               WHERE source_id = ? AND external_id = ?""",
            (source_id, external_id),
        ).fetchone()

    def observe(
        self,
        *,
        source_code: str,
        external_id: str,
        canonical_url: str,
        record_type: str,
        content_hash: str,
        grant_call_id: str | None = None,
        now: datetime | None = None,
    ) -> SourceRecordObservation:
        if not external_id.strip():
            raise ValueError("external_id must not be empty")
        if not canonical_url.strip():
            raise ValueError("canonical_url must not be empty")
        if not record_type.strip():
            raise ValueError("record_type must not be empty")
        self._validate_hash(content_hash)

        source_id = self._source_id(source_code)
        timestamp = _utc(now).isoformat()

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._get_by_identity(source_id, external_id)
            previous_hash: str | None = None

            if existing is None:
                record_id = source_id + ":" + external_id
                self.connection.execute(
                    """INSERT INTO source_records(
                         id, source_id, external_id, canonical_url, record_type,
                         grant_call_id, first_seen_at, last_seen_at,
                         presence_state, missing_run_count, content_hash
                       ) VALUES (
                         ?, ?, ?, ?, ?, ?, ?, ?,
                         'SEEN', 0, ?
                       )""",
                    (
                        record_id,
                        source_id,
                        external_id,
                        canonical_url,
                        record_type,
                        grant_call_id,
                        timestamp,
                        timestamp,
                        content_hash,
                    ),
                )
                change = SourceRecordChange.NEW
            else:
                (
                    record_id,
                    _old_url,
                    _old_type,
                    old_hash,
                    _first_seen,
                    _last_seen,
                    _presence,
                    _missing_count,
                    old_grant_call_id,
                ) = existing
                previous_hash = str(old_hash) if old_hash is not None else None
                change = (
                    SourceRecordChange.NOT_MODIFIED
                    if previous_hash == content_hash
                    else SourceRecordChange.CHANGED
                )
                linked_grant = (
                    grant_call_id
                    if grant_call_id is not None
                    else old_grant_call_id
                )
                self.connection.execute(
                    """UPDATE source_records
                       SET canonical_url = ?,
                           record_type = ?,
                           grant_call_id = ?,
                           last_seen_at = ?,
                           presence_state = 'SEEN',
                           missing_run_count = 0,
                           content_hash = ?
                       WHERE source_id = ? AND external_id = ?""",
                    (
                        canonical_url,
                        record_type,
                        linked_grant,
                        timestamp,
                        content_hash,
                        source_id,
                        external_id,
                    ),
                )

            row = self._get_by_identity(source_id, external_id)
            if row is None:
                raise RuntimeError("source record observation was not persisted")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        (
            record_id,
            stored_url,
            stored_type,
            stored_hash,
            first_seen_at,
            last_seen_at,
            presence_state,
            missing_run_count,
            stored_grant_call_id,
        ) = row
        return SourceRecordObservation(
            record_id=str(record_id),
            source_code=source_code,
            external_id=external_id,
            canonical_url=str(stored_url),
            record_type=str(stored_type),
            content_hash=str(stored_hash),
            change=change,
            first_seen_at=str(first_seen_at),
            last_seen_at=str(last_seen_at),
            presence_state=str(presence_state),
            missing_run_count=int(missing_run_count),
            grant_call_id=(
                str(stored_grant_call_id)
                if stored_grant_call_id is not None
                else None
            ),
            previous_content_hash=previous_hash,
        )

    def link_grant_call(
        self,
        *,
        source_code: str,
        external_id: str,
        grant_call_id: str,
    ) -> None:
        if not grant_call_id.strip():
            raise ValueError("grant_call_id must not be empty")
        source_id = self._source_id(source_code)
        result = self.connection.execute(
            """UPDATE source_records
               SET grant_call_id = ?
               WHERE source_id = ? AND external_id = ?""",
            (grant_call_id, source_id, external_id),
        )
        if result.rowcount != 1:
            self.connection.rollback()
            raise KeyError((source_code, external_id))
        self.connection.commit()
