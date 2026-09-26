import hashlib
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.source_records import (
    SourceRecordChange,
    SqliteSourceRecordRepository,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SourceRecordRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.connection.executescript(path.read_text(encoding="utf-8"))
        self.connection.execute(
            """INSERT INTO source_registry(
                 id,code,name,base_url,adapter_key,authority,retrieval_mode,
                 refresh_minutes,enabled,priority
               ) VALUES (
                 'src','TEST','Test source','https://example.test/',
                 'test','OFFICIAL','JSON',60,1,10
               )"""
        )
        self.connection.commit()
        self.repo = SqliteSourceRecordRepository(self.connection)
        self.t0 = datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc)

    def observe(self, content="v1", now=None):
        return self.repo.observe(
            source_code="TEST",
            external_id="call-1",
            canonical_url="https://example.test/calls/1",
            record_type="GRANT_CALL",
            content_hash=digest(content),
            now=now or self.t0,
        )

    def test_new_then_identical_is_not_modified(self):
        first = self.observe()
        second = self.observe(
            now=datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(first.change, SourceRecordChange.NEW)
        self.assertEqual(second.change, SourceRecordChange.NOT_MODIFIED)
        self.assertEqual(first.record_id, second.record_id)
        self.assertEqual(first.first_seen_at, second.first_seen_at)
        self.assertNotEqual(first.last_seen_at, second.last_seen_at)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
            1,
        )

    def test_changed_hash_is_detected_without_changing_identity(self):
        first = self.observe("v1")
        changed = self.observe(
            "v2",
            now=datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(changed.change, SourceRecordChange.CHANGED)
        self.assertEqual(changed.record_id, first.record_id)
        self.assertEqual(changed.previous_content_hash, digest("v1"))
        self.assertEqual(changed.content_hash, digest("v2"))

    def test_observation_resets_missing_state(self):
        observed = self.observe()
        self.connection.execute(
            """UPDATE source_records
               SET presence_state='MISSING_CANDIDATE', missing_run_count=2
               WHERE id=?""",
            (observed.record_id,),
        )
        self.connection.commit()

        restored = self.observe(
            now=datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(restored.presence_state, "SEEN")
        self.assertEqual(restored.missing_run_count, 0)

    def test_existing_grant_link_is_preserved_when_observation_omits_it(self):
        self.connection.execute(
            "INSERT INTO providers(id,name,provider_type) VALUES ('p','P','NATIONAL')"
        )
        self.connection.execute(
            """INSERT INTO programmes(id,provider_id,name,funding_origin)
               VALUES ('pr','p','Program','CZ_NATIONAL')"""
        )
        self.connection.execute(
            """INSERT INTO grant_calls(
                 id,programme_id,canonical_slug,current_status,current_title,
                 first_seen_at,created_at,updated_at
               ) VALUES (
                 'g','pr','g','OPEN','Grant','2026-01-01','2026-01-01','2026-01-01'
               )"""
        )
        self.connection.commit()

        observed = self.repo.observe(
            source_code="TEST",
            external_id="call-1",
            canonical_url="https://example.test/calls/1",
            record_type="GRANT_CALL",
            content_hash=digest("v1"),
            grant_call_id="g",
            now=self.t0,
        )
        repeated = self.observe("v1")
        self.assertEqual(observed.grant_call_id, "g")
        self.assertEqual(repeated.grant_call_id, "g")

    def test_link_grant_call_is_fk_guarded(self):
        observed = self.observe()
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.link_grant_call(
                source_code="TEST",
                external_id="call-1",
                grant_call_id="missing",
            )
        row = self.connection.execute(
            "SELECT grant_call_id FROM source_records WHERE id=?",
            (observed.record_id,),
        ).fetchone()
        self.assertIsNone(row[0])

    def test_invalid_hash_fails_before_mutation(self):
        with self.assertRaises(ValueError):
            self.repo.observe(
                source_code="TEST",
                external_id="bad",
                canonical_url="https://example.test/bad",
                record_type="GRANT_CALL",
                content_hash="BAD",
                now=self.t0,
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
