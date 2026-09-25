from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .state import PresenceState


@dataclass(frozen=True, slots=True)
class PresenceRecord:
    source_record_id: str
    external_id: str
    state: PresenceState
    missing_run_count: int
    grant_call_id: str | None


@dataclass(frozen=True, slots=True)
class PresenceReconciliationResult:
    source_id: str
    seen: int = 0
    missing_candidates: int = 0
    confirmed_missing: int = 0
    restored: int = 0
    unchanged: int = 0
    destructive_updates_blocked: int = 0


class SqlitePresenceRepository:
    """Persistence for source-record presence state.

    This repository updates only source_records presence metadata.
    It intentionally never mutates grant_calls.current_status.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")

    def list_for_source(self, source_id: str) -> list[PresenceRecord]:
        rows = self.connection.execute(
            """SELECT id, external_id, presence_state, missing_run_count, grant_call_id
               FROM source_records
               WHERE source_id = ?
               ORDER BY external_id""",
            (source_id,),
        ).fetchall()
        return [
            PresenceRecord(
                source_record_id=str(row[0]),
                external_id=str(row[1]),
                state=PresenceState(str(row[2])),
                missing_run_count=int(row[3]),
                grant_call_id=(str(row[4]) if row[4] is not None else None),
            )
            for row in rows
        ]

    def mark_seen(
        self,
        source_record_id: str,
        *,
        now: datetime,
    ) -> None:
        current = _utc(now).isoformat()
        result = self.connection.execute(
            """UPDATE source_records
               SET presence_state = 'SEEN',
                   missing_run_count = 0,
                   last_seen_at = ?
               WHERE id = ?""",
            (current, source_record_id),
        )
        if result.rowcount != 1:
            raise RuntimeError("source record not found during mark_seen")

    def mark_missing(
        self,
        source_record_id: str,
        *,
        state: PresenceState,
        missing_run_count: int,
    ) -> None:
        if state not in {
            PresenceState.MISSING_CANDIDATE,
            PresenceState.CONFIRMED_MISSING,
        }:
            raise ValueError("missing transition requires a missing state")
        if missing_run_count < 1:
            raise ValueError("missing_run_count must be >= 1")

        result = self.connection.execute(
            """UPDATE source_records
               SET presence_state = ?,
                   missing_run_count = ?
               WHERE id = ?""",
            (state.value, missing_run_count, source_record_id),
        )
        if result.rowcount != 1:
            raise RuntimeError("source record not found during mark_missing")

    def commit(self) -> None:
        self.connection.commit()


class PresenceReconciler:
    """Reconcile one successful discovery run against persisted source records.

    Missing source records affect only source presence. Canonical call status is
    deliberately outside this component and may change only from authoritative
    source evidence handled by normalization/versioning.
    """

    def __init__(
        self,
        repository: SqlitePresenceRepository,
        *,
        confirmation_runs: int = 3,
    ) -> None:
        if confirmation_runs < 1:
            raise ValueError("confirmation_runs must be >= 1")
        self.repository = repository
        self.confirmation_runs = confirmation_runs

    def reconcile(
        self,
        *,
        source_id: str,
        seen_external_ids: Iterable[str],
        destructive_changes_allowed: bool,
        now: datetime | None = None,
    ) -> PresenceReconciliationResult:
        current = _utc(now)
        seen_ids = {str(value) for value in seen_external_ids}
        records = self.repository.list_for_source(source_id)

        seen = 0
        missing_candidates = 0
        confirmed_missing = 0
        restored = 0
        unchanged = 0
        blocked = 0

        for record in records:
            if record.external_id in seen_ids:
                if (
                    record.state != PresenceState.SEEN
                    or record.missing_run_count != 0
                ):
                    restored += 1
                    self.repository.mark_seen(
                        record.source_record_id,
                        now=current,
                    )
                else:
                    seen += 1
                continue

            if not destructive_changes_allowed:
                blocked += 1
                continue

            if record.state == PresenceState.CONFIRMED_MISSING:
                unchanged += 1
                continue

            next_count = record.missing_run_count + 1
            next_state = (
                PresenceState.CONFIRMED_MISSING
                if next_count >= self.confirmation_runs
                else PresenceState.MISSING_CANDIDATE
            )
            self.repository.mark_missing(
                record.source_record_id,
                state=next_state,
                missing_run_count=next_count,
            )
            if next_state == PresenceState.CONFIRMED_MISSING:
                confirmed_missing += 1
            else:
                missing_candidates += 1

        self.repository.commit()
        return PresenceReconciliationResult(
            source_id=source_id,
            seen=seen,
            missing_candidates=missing_candidates,
            confirmed_missing=confirmed_missing,
            restored=restored,
            unchanged=unchanged,
            destructive_updates_blocked=blocked,
        )


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)
