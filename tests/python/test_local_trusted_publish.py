import hashlib
import sqlite3
from dataclasses import replace
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.local_publish import SearchableGrant
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from local_trusted_publish import (
    discover_local_d1_database,
    publish_grants_to_local_d1,
)


class TrustedLocalPublishTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.persist = self.root / "wrangler"
        self.persist.mkdir()
        self.database = self.persist / "state.sqlite"
        self.connection = sqlite3.connect(self.database)
        self.connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.connection.executescript(path.read_text(encoding="utf-8"))
        self.connection.close()

        self.raw_dir = self.root / "raw"
        self.store = LocalRawSnapshotStore(self.raw_dir)
        self.at = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
        self.snapshot = self.store.put(
            source_code="TEST",
            source_url="https://example.test/call/1",
            content=b'{"title":"Trusted local refresh"}',
            mime_type="application/json",
            retrieved_at=self.at,
        )

    def tearDown(self):
        self.temp.cleanup()

    def grant(self):
        return SearchableGrant(
            source_id="source:test",
            source_code="TEST",
            source_name="Test source",
            source_base_url="https://example.test/",
            adapter_key="test",
            source_external_id="call-1",
            source_url=self.snapshot.source_url,
            content_hash=self.snapshot.sha256,
            provider_id="provider:test",
            provider_name="Test provider",
            provider_type="NATIONAL",
            programme_id="programme:test",
            programme_name="Test programme",
            funding_origin="CZ_NATIONAL",
            grant_call_id="grant:test:call-1",
            grant_version_id="legacy-unused-id",
            canonical_slug="test-call-1",
            title="Trusted local refresh",
            summary="Digitalizace obce",
            status="OPEN",
            verification_status="AUTO_EXTRACTED",
            captured_at=self.at.isoformat(),
            submission_close_at="2027-01-01T00:00:00+00:00",
            supported_activities="digitalizace obce",
            keywords="digitalizace",
            retrieval_mode="JSON",
        )

    def test_discovers_only_migrated_d1_database(self):
        found = discover_local_d1_database(self.persist)
        self.assertEqual(found, self.database.resolve())

    def test_refuses_to_guess_between_multiple_migrated_databases(self):
        second = self.persist / "second.sqlite"
        source = sqlite3.connect(self.database)
        target = sqlite3.connect(second)
        source.backup(target)
        source.close()
        target.close()
        with self.assertRaisesRegex(RuntimeError, "Multiple migrated"):
            discover_local_d1_database(self.persist)

    def test_trusted_publish_creates_provenance_and_search_via_outbox(self):
        summary = publish_grants_to_local_d1(
            [self.grant()],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            now=self.at,
        )
        self.assertEqual(summary.grants, 1)
        self.assertEqual(summary.search_events_delivered, 1)

        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT state FROM canonical_staging_items"
                ).fetchone()[0],
                "PUBLISHED",
            )
            version_id = connection.execute(
                "SELECT current_version_id FROM grant_calls WHERE id='grant:test:call-1'"
            ).fetchone()[0]
            self.assertIsNotNone(version_id)
            self.assertGreaterEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM field_evidence WHERE entity_id=?",
                    (version_id,),
                ).fetchone()[0],
                3,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM document_versions"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM grant_search_documents"
                ).fetchone()[0],
                1,
            )
            statuses = dict(
                connection.execute(
                    "SELECT event_type,status FROM outbox_events"
                ).fetchall()
            )
            self.assertEqual(
                statuses["SEARCH_REINDEX_REQUIRED"],
                "DELIVERED",
            )
            self.assertEqual(
                statuses["CHANGE_DETECTION_REQUIRED"],
                "PENDING",
            )
        finally:
            connection.close()

    def test_retry_is_idempotent_and_does_not_redeliver_search_event(self):
        first = publish_grants_to_local_d1(
            [self.grant()],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            now=self.at,
        )
        second = publish_grants_to_local_d1(
            [self.grant()],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            now=self.at,
        )
        self.assertEqual(first.search_events_delivered, 1)
        self.assertEqual(second.search_events_delivered, 0)

        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM grant_call_versions"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM canonical_staging_items"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM outbox_events"
                ).fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_missing_raw_snapshot_fails_before_canonical_publish(self):
        bad = self.grant()
        missing_hash = hashlib.sha256(b"missing").hexdigest()
        bad = replace(bad, content_hash=missing_hash)
        with self.assertRaises(FileNotFoundError):
            publish_grants_to_local_d1(
                [bad],
                raw_dir=self.raw_dir,
                persist_root=self.persist,
                now=self.at,
            )


if __name__ == "__main__":
    unittest.main()
