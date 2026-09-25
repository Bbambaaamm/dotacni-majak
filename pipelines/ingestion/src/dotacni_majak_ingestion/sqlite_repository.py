from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from dotacni_majak_source_sdk import SourceCheckpoint

from .orchestrator import (
    IngestionItemRecord,
    IngestionRepository,
    IngestionRunSummary,
)
from .state import IngestionState


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return _utc(value).isoformat()


def _checkpoint_json(checkpoint: SourceCheckpoint | None) -> str | None:
    if checkpoint is None:
        return None
    return json.dumps(
        checkpoint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SqliteIngestionRepository(IngestionRepository):
    """Persistent ingestion repository using D1-compatible SQLite SQL.

    Heavy ingestion runs outside Workers, so the reference implementation uses
    Python sqlite3. The migration and queries intentionally stay in the D1
    compatible subset so a remote D1 transport can implement the same contract
    without changing the orchestrator.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.connection = connection
        self.run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.connection.execute("PRAGMA foreign_keys = ON")

    def _now(self) -> datetime:
        return _utc(self._clock())

    def get_checkpoint(self, source_code: str) -> SourceCheckpoint | None:
        row = self.connection.execute(
            """SELECT cursor, updated_after, opaque_state_json
               FROM source_checkpoints
               WHERE source_code = ?""",
            (source_code,),
        ).fetchone()
        if row is None:
            return None
        cursor, updated_after, opaque_json = row
        return SourceCheckpoint(
            cursor=cursor,
            updated_after=(
                datetime.fromisoformat(updated_after)
                if updated_after
                else None
            ),
            opaque_state=json.loads(opaque_json or "{}"),
        )

    def set_checkpoint(
        self,
        source_code: str,
        checkpoint: SourceCheckpoint,
    ) -> None:
        now = _iso(self._now())
        updated_after = (
            checkpoint.updated_after.isoformat()
            if checkpoint.updated_after
            else None
        )
        opaque_json = json.dumps(
            checkpoint.opaque_state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.connection.execute(
            """INSERT INTO source_checkpoints(
                 source_code, cursor, updated_after, opaque_state_json, updated_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(source_code) DO UPDATE SET
                 cursor = excluded.cursor,
                 updated_after = excluded.updated_after,
                 opaque_state_json = excluded.opaque_state_json,
                 updated_at = excluded.updated_at""",
            (
                source_code,
                checkpoint.cursor,
                updated_after,
                opaque_json,
                now,
            ),
        )
        self.connection.commit()

    def get_or_create_item(
        self,
        source_code: str,
        external_id: str,
    ) -> IngestionItemRecord:
        now = _iso(self._now())
        self.connection.execute(
            """INSERT OR IGNORE INTO ingestion_items(
                 source_code, external_id, state, attempts, last_error,
                 first_seen_run_id, last_run_id, created_at, updated_at
               ) VALUES (?, ?, 'DISCOVERED', 0, NULL, ?, ?, ?, ?)""",
            (
                source_code,
                external_id,
                self.run_id,
                self.run_id,
                now,
                now,
            ),
        )
        # COMPLETED is idempotent only inside one ingestion run. A later
        # run must re-check the same source identity because the upstream
        # record may have changed and require a new immutable version.
        self.connection.execute(
            """UPDATE ingestion_items
               SET state = CASE
                     WHEN last_run_id IS NOT ? THEN 'DISCOVERED'
                     ELSE state
                   END,
                   attempts = CASE
                     WHEN last_run_id IS NOT ? THEN 0
                     ELSE attempts
                   END,
                   last_error = CASE
                     WHEN last_run_id IS NOT ? THEN NULL
                     ELSE last_error
                   END,
                   last_run_id = ?,
                   updated_at = ?
               WHERE source_code = ? AND external_id = ?""",
            (
                self.run_id,
                self.run_id,
                self.run_id,
                self.run_id,
                now,
                source_code,
                external_id,
            ),
        )
        self.connection.commit()
        row = self.connection.execute(
            """SELECT state, attempts, last_error
               FROM ingestion_items
               WHERE source_code = ? AND external_id = ?""",
            (source_code, external_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to persist ingestion item")
        state, attempts, last_error = row
        return IngestionItemRecord(
            source_code=source_code,
            external_id=external_id,
            state=IngestionState(state),
            attempts=attempts,
            last_error=last_error,
        )

    def transition(
        self,
        item: IngestionItemRecord,
        state: IngestionState,
    ) -> None:
        now = _iso(self._now())
        result = self.connection.execute(
            """UPDATE ingestion_items
               SET state = ?, last_error = NULL, last_run_id = ?, updated_at = ?
               WHERE source_code = ? AND external_id = ?""",
            (
                state.value,
                self.run_id,
                now,
                item.source_code,
                item.external_id,
            ),
        )
        if result.rowcount != 1:
            raise RuntimeError("ingestion item transition target not found")
        self.connection.commit()
        item.state = state
        item.last_error = None

    def fail(
        self,
        item: IngestionItemRecord,
        error: Exception,
    ) -> None:
        now = _iso(self._now())
        message = f"{type(error).__name__}: {error}"
        result = self.connection.execute(
            """UPDATE ingestion_items
               SET state = 'RETRYABLE_FAILED',
                   attempts = attempts + 1,
                   last_error = ?,
                   last_run_id = ?,
                   updated_at = ?
               WHERE source_code = ? AND external_id = ?""",
            (
                message,
                self.run_id,
                now,
                item.source_code,
                item.external_id,
            ),
        )
        if result.rowcount != 1:
            raise RuntimeError("ingestion item failure target not found")
        self.connection.commit()
        item.attempts += 1
        item.last_error = message
        item.state = IngestionState.RETRYABLE_FAILED

    def acquire_lock(
        self,
        source_code: str,
        owner: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        current = _utc(now)
        expires = current + timedelta(seconds=lease_seconds)
        now_iso = current.isoformat()
        expires_iso = expires.isoformat()

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                """SELECT lease_owner, lease_expires_at
                   FROM ingestion_locks
                   WHERE source_code = ?""",
                (source_code,),
            ).fetchone()

            if row is not None:
                lease_owner, lease_expires_at = row
                if (
                    lease_owner != owner
                    and datetime.fromisoformat(lease_expires_at) > current
                ):
                    self.connection.rollback()
                    return False

            self.connection.execute(
                """INSERT INTO ingestion_locks(
                     source_code, lease_owner, lease_expires_at,
                     acquired_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(source_code) DO UPDATE SET
                     lease_owner = excluded.lease_owner,
                     lease_expires_at = excluded.lease_expires_at,
                     acquired_at = CASE
                       WHEN ingestion_locks.lease_owner = excluded.lease_owner
                       THEN ingestion_locks.acquired_at
                       ELSE excluded.acquired_at
                     END,
                     updated_at = excluded.updated_at""",
                (
                    source_code,
                    owner,
                    expires_iso,
                    now_iso,
                    now_iso,
                ),
            )
            self.connection.commit()
            return True
        except Exception:
            self.connection.rollback()
            raise

    def renew_lock(
        self,
        source_code: str,
        owner: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        current = _utc(now)
        expires = current + timedelta(seconds=lease_seconds)
        result = self.connection.execute(
            """UPDATE ingestion_locks
               SET lease_expires_at = ?, updated_at = ?
               WHERE source_code = ?
                 AND lease_owner = ?
                 AND lease_expires_at > ?""",
            (
                expires.isoformat(),
                current.isoformat(),
                source_code,
                owner,
                current.isoformat(),
            ),
        )
        self.connection.commit()
        return result.rowcount == 1

    def release_lock(self, source_code: str, owner: str) -> None:
        self.connection.execute(
            """DELETE FROM ingestion_locks
               WHERE source_code = ? AND lease_owner = ?""",
            (source_code, owner),
        )
        self.connection.commit()

    def start_run(
        self,
        source_code: str,
        *,
        started_at: datetime,
        checkpoint_before: SourceCheckpoint | None,
    ) -> None:
        self.connection.execute(
            """INSERT INTO ingestion_runs(
                 id, source_code, status, started_at, checkpoint_before_json
               ) VALUES (?, ?, 'RUNNING', ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 source_code = excluded.source_code,
                 status = 'RUNNING',
                 started_at = excluded.started_at,
                 finished_at = NULL,
                 checkpoint_before_json = excluded.checkpoint_before_json,
                 checkpoint_after_json = NULL,
                 processed = 0,
                 skipped = 0,
                 gone = 0,
                 failed = 0,
                 pages = 0,
                 last_error = NULL""",
            (
                self.run_id,
                source_code,
                _iso(started_at),
                _checkpoint_json(checkpoint_before),
            ),
        )
        self.connection.commit()

    def finish_run(
        self,
        summary: IngestionRunSummary,
        *,
        finished_at: datetime,
        checkpoint_after: SourceCheckpoint | None,
        last_error: str | None = None,
    ) -> None:
        result = self.connection.execute(
            """UPDATE ingestion_runs
               SET status = ?,
                   finished_at = ?,
                   checkpoint_after_json = ?,
                   processed = ?,
                   skipped = ?,
                   gone = ?,
                   failed = ?,
                   pages = ?,
                   last_error = ?
               WHERE id = ?""",
            (
                summary.status.value,
                _iso(finished_at),
                _checkpoint_json(checkpoint_after),
                summary.processed,
                summary.skipped,
                summary.gone,
                summary.failed,
                summary.pages,
                last_error,
                self.run_id,
            ),
        )
        if result.rowcount != 1:
            raise RuntimeError("ingestion run audit row not found")
        self.connection.commit()
