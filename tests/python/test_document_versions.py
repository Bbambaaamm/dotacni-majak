import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.document_versions import (
    DocumentVersionChange,
    SqliteDocumentVersionRepository,
)
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore


class DocumentVersionRepositoryTest(unittest.TestCase):
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
                 'test','OFFICIAL','HTML',60,1,10
               )"""
        )
        self.connection.commit()
        self.repo = SqliteDocumentVersionRepository(self.connection)
        self.temp = tempfile.TemporaryDirectory()
        self.store = LocalRawSnapshotStore(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, content, *, url="https://example.test/a.pdf", hour=10):
        return self.store.put(
            source_code="TEST",
            source_url=url,
            content=content,
            mime_type="application/pdf",
            retrieved_at=datetime(2026, 9, 26, hour, 0, tzinfo=timezone.utc),
        )

    def test_same_content_is_same_immutable_version(self):
        snap = self.snapshot(b"same")
        first = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="GUIDELINES",
            snapshot=snap,
            title="Rules",
        )
        second = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="GUIDELINES",
            snapshot=snap,
            title="Rules updated label",
        )
        self.assertEqual(first.change, DocumentVersionChange.NEW_DOCUMENT)
        self.assertEqual(second.change, DocumentVersionChange.NOT_MODIFIED)
        self.assertEqual(first.source_document_id, second.source_document_id)
        self.assertEqual(first.document_version_id, second.document_version_id)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM document_versions"
            ).fetchone()[0],
            1,
        )

    def test_changed_bytes_create_new_version_of_same_document(self):
        first = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="CALL_DOCUMENT",
            snapshot=self.snapshot(b"v1", hour=10),
        )
        second = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="CALL_DOCUMENT",
            snapshot=self.snapshot(b"v2", hour=11),
        )
        self.assertEqual(second.change, DocumentVersionChange.NEW_VERSION)
        self.assertEqual(first.source_document_id, second.source_document_id)
        self.assertNotEqual(first.document_version_id, second.document_version_id)
        latest = self.repo.latest(first.source_document_id)
        self.assertEqual(latest.document_version_id, second.document_version_id)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM document_versions"
            ).fetchone()[0],
            2,
        )

    def test_role_is_part_of_stable_document_identity(self):
        snap = self.snapshot(b"same")
        a = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="GUIDELINES",
            snapshot=snap,
        )
        b = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="ANNEX",
            snapshot=snap,
        )
        self.assertNotEqual(a.source_document_id, b.source_document_id)

    def test_source_url_is_part_of_stable_document_identity(self):
        a = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="ANNEX",
            snapshot=self.snapshot(b"same", url="https://example.test/a.pdf"),
        )
        b = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="ANNEX",
            snapshot=self.snapshot(b"same", url="https://example.test/b.pdf"),
        )
        self.assertNotEqual(a.source_document_id, b.source_document_id)

    def test_existing_grant_link_is_not_erased_by_later_observation(self):
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

        snap = self.snapshot(b"same")
        first = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="CALL_DOCUMENT",
            snapshot=snap,
            grant_call_id="g",
        )
        second = self.repo.observe_snapshot(
            source_code="TEST",
            document_type="CALL_DOCUMENT",
            snapshot=snap,
        )
        self.assertEqual(first.grant_call_id, "g")
        self.assertEqual(second.grant_call_id, "g")

    def test_snapshot_source_mismatch_fails_closed(self):
        snap = self.snapshot(b"x")
        with self.assertRaises(ValueError):
            self.repo.observe_snapshot(
                source_code="OTHER",
                document_type="ANNEX",
                snapshot=snap,
            )


if __name__ == "__main__":
    unittest.main()
