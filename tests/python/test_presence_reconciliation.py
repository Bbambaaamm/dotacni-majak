import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.presence import (
    PresenceReconciler,
    SqlitePresenceRepository,
)
from dotacni_majak_ingestion.state import PresenceState


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))

    connection.execute(
        """INSERT INTO source_registry(
             id, code, name, base_url, adapter_key, authority,
             retrieval_mode, refresh_minutes, enabled, priority
           ) VALUES (
             'src', 'TEST', 'Test', 'https://example.com', 'test',
             'OFFICIAL', 'HTML', 60, 1, 1
           )"""
    )
    connection.execute(
        "INSERT INTO providers(id,name,provider_type) VALUES ('p','Provider','NATIONAL')"
    )
    connection.execute(
        """INSERT INTO programmes(id,provider_id,name,funding_origin)
           VALUES ('pr','p','Programme','CZ_NATIONAL')"""
    )
    connection.execute(
        """INSERT INTO grant_calls(
             id,programme_id,canonical_slug,current_status,current_title,
             first_seen_at,created_at,updated_at
           ) VALUES (
             'g','pr','grant','OPEN','Grant',
             '2026-09-01T00:00:00+00:00',
             '2026-09-01T00:00:00+00:00',
             '2026-09-01T00:00:00+00:00'
           )"""
    )
    for record_id, external_id in (("r1", "a"), ("r2", "b")):
        connection.execute(
            """INSERT INTO source_records(
                 id,source_id,external_id,canonical_url,record_type,grant_call_id,
                 first_seen_at,last_seen_at,presence_state,missing_run_count
               ) VALUES (
                 ?, 'src', ?, ?, 'GRANT_CALL', 'g',
                 '2026-09-01T00:00:00+00:00',
                 '2026-09-01T00:00:00+00:00',
                 'SEEN', 0
               )""",
            (record_id, external_id, f"https://example.com/{external_id}"),
        )
    connection.commit()
    return connection


class PresenceReconcilerTest(unittest.TestCase):
    def test_missing_record_progresses_only_after_threshold(self):
        connection = migrated_connection()
        repo = SqlitePresenceRepository(connection)
        reconciler = PresenceReconciler(repo, confirmation_runs=3)

        for expected_state, expected_count in (
            (PresenceState.MISSING_CANDIDATE, 1),
            (PresenceState.MISSING_CANDIDATE, 2),
            (PresenceState.CONFIRMED_MISSING, 3),
        ):
            reconciler.reconcile(
                source_id="src",
                seen_external_ids={"a"},
                destructive_changes_allowed=True,
                now=NOW,
            )
            record = {r.external_id: r for r in repo.list_for_source("src")}["b"]
            self.assertEqual(record.state, expected_state)
            self.assertEqual(record.missing_run_count, expected_count)

        grant_status = connection.execute(
            "SELECT current_status FROM grant_calls WHERE id='g'"
        ).fetchone()[0]
        self.assertEqual(grant_status, "OPEN")

    def test_degraded_run_does_not_advance_missing_state(self):
        connection = migrated_connection()
        repo = SqlitePresenceRepository(connection)
        reconciler = PresenceReconciler(repo, confirmation_runs=2)

        result = reconciler.reconcile(
            source_id="src",
            seen_external_ids=set(),
            destructive_changes_allowed=False,
            now=NOW,
        )

        states = repo.list_for_source("src")
        self.assertEqual(result.destructive_updates_blocked, 2)
        self.assertTrue(all(r.state == PresenceState.SEEN for r in states))
        self.assertTrue(all(r.missing_run_count == 0 for r in states))

    def test_reappearance_resets_missing_state_and_counter(self):
        connection = migrated_connection()
        repo = SqlitePresenceRepository(connection)
        reconciler = PresenceReconciler(repo, confirmation_runs=2)

        reconciler.reconcile(
            source_id="src",
            seen_external_ids={"a"},
            destructive_changes_allowed=True,
            now=NOW,
        )
        reconciler.reconcile(
            source_id="src",
            seen_external_ids={"a"},
            destructive_changes_allowed=True,
            now=NOW,
        )
        missing = {r.external_id: r for r in repo.list_for_source("src")}["b"]
        self.assertEqual(missing.state, PresenceState.CONFIRMED_MISSING)

        result = reconciler.reconcile(
            source_id="src",
            seen_external_ids={"a", "b"},
            destructive_changes_allowed=True,
            now=NOW,
        )
        restored = {r.external_id: r for r in repo.list_for_source("src")}["b"]
        self.assertEqual(result.restored, 1)
        self.assertEqual(restored.state, PresenceState.SEEN)
        self.assertEqual(restored.missing_run_count, 0)


if __name__ == "__main__":
    unittest.main()
