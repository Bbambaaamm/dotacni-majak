import hashlib
import json
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.staging import (
    SqliteCanonicalStagingRepository,
    StagingProvenanceStatus,
    StagingState,
    StagingValidationStatus,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CanonicalStagingRepositoryTest(unittest.TestCase):
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
        self.repo = SqliteCanonicalStagingRepository(self.connection)
        self.t0 = datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc)

    def stage(self, *, payload=None, hash_value=None, retry=False, provenance=None):
        payload = payload or {"title": "Grant"}
        return self.repo.stage(
            source_code="TEST",
            external_id="call-1",
            entity_type="GRANT_CALL",
            canonical_identity="grant:test:call-1",
            payload=payload,
            content_hash=hash_value or digest(json.dumps(payload, sort_keys=True)),
            provenance_status=provenance or StagingProvenanceStatus.COMPLETE,
            retry=retry,
            now=self.t0,
        )

    def test_same_content_is_idempotent(self):
        first = self.stage()
        second = self.stage()
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_staging_items"
            ).fetchone()[0],
            1,
        )

    def test_changed_content_creates_distinct_candidate(self):
        first = self.stage()
        second = self.stage(
            payload={"title": "Grant changed"},
            hash_value=digest("changed"),
        )
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_staging_items"
            ).fetchone()[0],
            2,
        )

    def test_missing_provenance_fails_closed(self):
        candidate = self.stage(
            provenance=StagingProvenanceStatus.MISSING,
        )
        with self.assertRaises(ValueError):
            self.repo.mark_validation(
                candidate.id,
                StagingValidationStatus.VALID,
                now=self.t0,
            )
        current = self.repo.get(candidate.id)
        self.assertEqual(current.state, StagingState.STAGED)
        self.assertEqual(
            current.validation_status,
            StagingValidationStatus.PENDING,
        )

    def test_valid_candidate_becomes_ready_then_published_idempotently(self):
        candidate = self.stage()
        ready = self.repo.mark_validation(
            candidate.id,
            StagingValidationStatus.VALID,
            now=self.t0,
        )
        self.assertEqual(ready.state, StagingState.READY)

        published = self.repo.mark_published(
            ready.id,
            published_entity_id="grant:test:call-1",
            now=self.t0,
        )
        again = self.repo.mark_published(
            ready.id,
            published_entity_id="grant:test:call-1",
            now=self.t0,
        )
        self.assertEqual(published, again)
        self.assertEqual(published.state, StagingState.PUBLISHED)

    def test_rejected_candidate_can_be_explicitly_retried(self):
        candidate = self.stage()
        rejected = self.repo.mark_validation(
            candidate.id,
            StagingValidationStatus.INVALID,
            error="schema mismatch",
            now=self.t0,
        )
        self.assertEqual(rejected.state, StagingState.REJECTED)

        retried = self.stage(retry=True)
        self.assertEqual(retried.id, candidate.id)
        self.assertEqual(retried.state, StagingState.STAGED)
        self.assertEqual(
            retried.validation_status,
            StagingValidationStatus.PENDING,
        )
        self.assertEqual(retried.attempts, 1)
        self.assertIsNone(retried.last_error)

    def test_cleanup_removes_only_old_terminal_rows(self):
        candidate = self.stage()
        rejected = self.repo.mark_validation(
            candidate.id,
            StagingValidationStatus.INVALID,
            error="bad",
            now=self.t0,
        )
        self.connection.execute(
            "UPDATE canonical_staging_items SET updated_at=? WHERE id=?",
            ("2026-01-01T00:00:00+00:00", rejected.id),
        )
        self.connection.commit()

        kept = self.repo.stage(
            source_code="TEST",
            external_id="call-2",
            entity_type="GRANT_CALL",
            canonical_identity="grant:test:call-2",
            payload={"title": "Pending"},
            content_hash=digest("pending"),
            provenance_status=StagingProvenanceStatus.COMPLETE,
            now=self.t0,
        )

        removed = self.repo.cleanup_terminal_before(
            datetime(2026, 6, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(removed, 1)
        self.assertIsNone(self.repo.get(rejected.id))
        self.assertIsNotNone(self.repo.get(kept.id))

    def test_database_rejects_invalid_hash(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO canonical_staging_items(
                     id,source_id,external_id,entity_type,canonical_identity,
                     payload_json,content_hash,validation_status,
                     provenance_status,state,created_at,updated_at
                   ) VALUES (
                     'bad','src','x','GRANT_CALL','g','{}','NOT-A-HASH',
                     'PENDING','COMPLETE','STAGED','x','x'
                   )"""
            )


if __name__ == "__main__":
    unittest.main()
