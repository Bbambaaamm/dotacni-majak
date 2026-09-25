import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.quarantine import QuarantineReason
from dotacni_majak_ingestion.quarantine_reprocess import QuarantineReprocessor
from dotacni_majak_ingestion.sqlite_quarantine import SqliteQuarantineRepository


NOW = datetime(2026, 9, 25, 13, 0, tzinfo=timezone.utc)


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
             'src', 'NSA', 'NSA', 'https://nsa.gov.cz', 'nsa',
             'OFFICIAL', 'HTML', 60, 1, 1
           )"""
    )
    connection.commit()
    return connection


class SqliteQuarantineRepositoryTest(unittest.TestCase):
    def test_persists_unresolved_item_and_raw_reference(self):
        connection = migrated_connection()
        repo = SqliteQuarantineRepository(connection)
        item = repo.add(
            source_code="NSA",
            external_id="16-2026",
            reason=QuarantineReason.VALIDATION_FAILED,
            details="bad deadline",
            payload_ref="raw/NSA/aa/bb/hash.bin",
            now=NOW,
        )

        reloaded = SqliteQuarantineRepository(connection).unresolved(source_code="NSA")
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].id, item.id)
        self.assertEqual(reloaded[0].payload_ref, "raw/NSA/aa/bb/hash.bin")
        self.assertEqual(reloaded[0].details, "bad deadline")

    def test_resolution_is_idempotent(self):
        connection = migrated_connection()
        repo = SqliteQuarantineRepository(connection)
        item = repo.add(
            source_code="NSA",
            reason=QuarantineReason.OTHER,
            payload_ref="raw:x",
            now=NOW,
        )
        first = repo.resolve(item.id, note="reviewed", now=NOW)
        second = repo.resolve(item.id, note="different", now=NOW)
        self.assertEqual(first.resolved_at, second.resolved_at)
        self.assertEqual(second.resolution_note, "reviewed")


class QuarantineReprocessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_records_audit_and_resolves_item(self):
        connection = migrated_connection()
        repo = SqliteQuarantineRepository(connection)
        item = repo.add(
            source_code="NSA",
            external_id="16-2026",
            reason=QuarantineReason.SCHEMA_MISMATCH,
            payload_ref="raw:abc",
            now=NOW,
        )
        seen = []

        async def handler(current):
            seen.append(current.payload_ref)

        service = QuarantineReprocessor(
            repository=repo,
            handler=handler,
            requested_by="test",
            parser_version="2.0",
            clock=lambda: NOW,
        )
        result = await service.reprocess(item.id)

        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(seen, ["raw:abc"])
        self.assertTrue(repo.get(item.id).is_resolved)
        attempts = repo.reprocess_attempts(item.id)
        self.assertEqual(attempts[0]["status"], "SUCCEEDED")
        self.assertEqual(attempts[0]["parser_version"], "2.0")

    async def test_failure_stays_unresolved_and_is_audited(self):
        connection = migrated_connection()
        repo = SqliteQuarantineRepository(connection)
        item = repo.add(
            source_code="NSA",
            reason=QuarantineReason.VALIDATION_FAILED,
            payload_ref="raw:abc",
            now=NOW,
        )

        async def handler(_):
            raise RuntimeError("still invalid")

        service = QuarantineReprocessor(
            repository=repo,
            handler=handler,
            requested_by="test",
            clock=lambda: NOW,
        )
        result = await service.reprocess(item.id)

        self.assertEqual(result.status, "FAILED")
        self.assertFalse(repo.get(item.id).is_resolved)
        attempts = repo.reprocess_attempts(item.id)
        self.assertEqual(attempts[0]["status"], "FAILED")
        self.assertIn("still invalid", attempts[0]["last_error"])


if __name__ == "__main__":
    unittest.main()
