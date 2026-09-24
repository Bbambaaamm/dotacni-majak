import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.orchestrator import (
    IngestionRunStatus,
    IngestionRunSummary,
)
from dotacni_majak_ingestion.sqlite_repository import SqliteIngestionRepository
from dotacni_majak_ingestion.state import IngestionState
from dotacni_majak_source_sdk import SourceCheckpoint


T0 = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


class SqliteIngestionRepositoryTest(unittest.TestCase):
    def test_checkpoint_survives_repository_restart(self):
        connection = migrated_connection()
        repo1 = SqliteIngestionRepository(
            connection,
            run_id="run-1",
            clock=lambda: T0,
        )
        checkpoint = SourceCheckpoint(
            cursor="page-7",
            updated_after=T0,
            opaque_state={"token": "abc", "pageSize": 50},
        )
        repo1.set_checkpoint("NSA", checkpoint)

        repo2 = SqliteIngestionRepository(
            connection,
            run_id="run-2",
            clock=lambda: T0 + timedelta(minutes=1),
        )
        restored = repo2.get_checkpoint("NSA")

        self.assertIsNotNone(restored)
        self.assertEqual(restored.cursor, "page-7")
        self.assertEqual(restored.updated_after, T0)
        self.assertEqual(restored.opaque_state, {"pageSize": 50, "token": "abc"})

    def test_item_state_and_attempts_survive_restart(self):
        connection = migrated_connection()
        repo1 = SqliteIngestionRepository(
            connection,
            run_id="run-1",
            clock=lambda: T0,
        )
        repo1.start_run("NSA", started_at=T0, checkpoint_before=None)
        item = repo1.get_or_create_item("NSA", "16/2026")
        repo1.transition(item, IngestionState.FETCHING)
        repo1.fail(item, ValueError("temporary"))

        repo2 = SqliteIngestionRepository(
            connection,
            run_id="run-2",
            clock=lambda: T0 + timedelta(minutes=1),
        )
        repo2.start_run(
            "NSA",
            started_at=T0 + timedelta(minutes=1),
            checkpoint_before=None,
        )
        restored = repo2.get_or_create_item("NSA", "16/2026")

        self.assertEqual(restored.state, IngestionState.RETRYABLE_FAILED)
        self.assertEqual(restored.attempts, 1)
        self.assertIn("ValueError: temporary", restored.last_error or "")

    def test_live_lease_blocks_other_owner_and_expired_lease_can_be_taken(self):
        connection = migrated_connection()
        repo1 = SqliteIngestionRepository(
            connection,
            run_id="run-a",
            clock=lambda: T0,
        )
        repo2 = SqliteIngestionRepository(
            connection,
            run_id="run-b",
            clock=lambda: T0,
        )

        self.assertTrue(
            repo1.acquire_lock(
                "NSA",
                "run-a",
                now=T0,
                lease_seconds=60,
            )
        )
        self.assertFalse(
            repo2.acquire_lock(
                "NSA",
                "run-b",
                now=T0 + timedelta(seconds=30),
                lease_seconds=60,
            )
        )
        self.assertTrue(
            repo2.acquire_lock(
                "NSA",
                "run-b",
                now=T0 + timedelta(seconds=61),
                lease_seconds=60,
            )
        )

        row = connection.execute(
            "SELECT lease_owner FROM ingestion_locks WHERE source_code = 'NSA'"
        ).fetchone()
        self.assertEqual(row[0], "run-b")

    def test_lease_renew_requires_current_unexpired_owner(self):
        connection = migrated_connection()
        repo = SqliteIngestionRepository(
            connection,
            run_id="run-a",
            clock=lambda: T0,
        )
        self.assertTrue(
            repo.acquire_lock("NSA", "run-a", now=T0, lease_seconds=60)
        )
        self.assertFalse(
            repo.renew_lock(
                "NSA",
                "other-owner",
                now=T0 + timedelta(seconds=10),
                lease_seconds=60,
            )
        )
        self.assertFalse(
            repo.renew_lock(
                "NSA",
                "run-a",
                now=T0 + timedelta(seconds=61),
                lease_seconds=60,
            )
        )

    def test_run_audit_persists_summary_and_checkpoints(self):
        connection = migrated_connection()
        repo = SqliteIngestionRepository(
            connection,
            run_id="run-1",
            clock=lambda: T0,
        )
        before = SourceCheckpoint(cursor="1")
        after = SourceCheckpoint(cursor="2", opaque_state={"done": True})
        repo.start_run("NSA", started_at=T0, checkpoint_before=before)
        repo.finish_run(
            IngestionRunSummary(
                source_code="NSA",
                status=IngestionRunStatus.COMPLETED,
                processed=8,
                skipped=2,
                gone=1,
                failed=0,
                pages=2,
            ),
            finished_at=T0 + timedelta(minutes=3),
            checkpoint_after=after,
        )

        row = connection.execute(
            """SELECT status, processed, skipped, gone, failed, pages,
                      checkpoint_before_json, checkpoint_after_json
               FROM ingestion_runs WHERE id = 'run-1'"""
        ).fetchone()
        self.assertEqual(row[:6], ("COMPLETED", 8, 2, 1, 0, 2))
        self.assertIn('"cursor":"1"', row[6])
        self.assertIn('"cursor":"2"', row[7])


if __name__ == "__main__":
    unittest.main()
