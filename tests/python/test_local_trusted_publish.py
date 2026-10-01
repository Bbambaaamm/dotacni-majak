import hashlib
import sqlite3
from dataclasses import replace
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.canonical_publisher import CanonicalPublicationError
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
            adapter_version="test-adapter-1.0",
            now=self.at,
        )
        self.assertEqual(summary.grants, 1)
        self.assertEqual(summary.search_events_delivered, 1)

        connection = sqlite3.connect(self.database)
        try:
            run = connection.execute(
                """SELECT status,records_seen,new_records,changed_records,
                          error_count,adapter_version
                   FROM source_runs WHERE id=?""",
                (summary.source_run_id,),
            ).fetchone()
            self.assertEqual(
                tuple(run),
                ("COMPLETED", 1, 1, 0, 0, "test-adapter-1.0"),
            )
            staged = connection.execute(
                """SELECT state,source_run_id
                   FROM canonical_staging_items"""
            ).fetchone()
            self.assertEqual(staged, ("PUBLISHED", summary.source_run_id))
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
            adapter_version="test-adapter-1.0",
            now=self.at,
        )
        second = publish_grants_to_local_d1(
            [self.grant()],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
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


    def test_reactivating_historical_raw_repoints_current_and_search(self):
        first = self.grant()
        first_summary = publish_grants_to_local_d1(
            [first],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=self.at,
        )
        self.assertEqual(first_summary.search_events_delivered, 1)

        second_at = self.at + timedelta(hours=1)
        second_snapshot = self.store.put(
            source_code="TEST",
            source_url=self.snapshot.source_url,
            content=b'{"title":"Trusted local refresh B"}',
            mime_type="application/json",
            retrieved_at=second_at,
        )
        second = replace(
            first,
            content_hash=second_snapshot.sha256,
            title="Trusted local refresh B",
            summary="Digitalizace obce B",
            captured_at=second_at.isoformat(),
        )
        second_summary = publish_grants_to_local_d1(
            [second],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=second_at,
        )
        self.assertEqual(second_summary.search_events_delivered, 1)

        reactivated_at = self.at + timedelta(hours=2)
        reactivated = publish_grants_to_local_d1(
            [first],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=reactivated_at,
        )
        self.assertEqual(reactivated.search_events_delivered, 1)

        repeated = publish_grants_to_local_d1(
            [first],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=self.at + timedelta(hours=3),
        )
        self.assertEqual(repeated.search_events_delivered, 0)

        connection = sqlite3.connect(self.database)
        try:
            current = connection.execute(
                """SELECT g.current_version_id,g.current_title,s.title
                   FROM grant_calls g
                   JOIN grant_search_documents s
                     ON s.grant_call_version_id=g.current_version_id
                   WHERE g.id='grant:test:call-1'"""
            ).fetchone()
            first_version = connection.execute(
                """SELECT id FROM grant_call_versions
                   WHERE grant_call_id='grant:test:call-1'
                     AND content_hash=?""",
                (first.content_hash,),
            ).fetchone()[0]
            self.assertEqual(
                current,
                (first_version, first.title, first.title),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM grant_call_versions"
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM outbox_events"
                ).fetchone()[0],
                6,
            )
        finally:
            connection.close()

    def test_same_raw_normalization_change_reprojects_without_new_version(self):
        first = self.grant()
        publish_grants_to_local_d1(
            [first],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=self.at,
        )
        corrected = replace(
            first,
            title="Trusted local refresh — corrected",
            summary="Corrected normalized summary",
            keywords="corrected normalization",
        )
        corrected_summary = publish_grants_to_local_d1(
            [corrected],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=self.at + timedelta(hours=1),
        )
        self.assertEqual(corrected_summary.search_events_delivered, 1)

        repeated = publish_grants_to_local_d1(
            [corrected],
            raw_dir=self.raw_dir,
            persist_root=self.persist,
            adapter_version="test-adapter-1.0",
            now=self.at + timedelta(hours=2),
        )
        self.assertEqual(repeated.search_events_delivered, 0)

        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM grant_call_versions"
                ).fetchone()[0],
                1,
            )
            title = connection.execute(
                """SELECT title FROM grant_search_documents"""
            ).fetchone()[0]
            self.assertEqual(title, corrected.title)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM outbox_events"
                ).fetchone()[0],
                4,
            )
        finally:
            connection.close()

    def test_source_batch_rolls_back_all_canonical_writes_on_late_failure(self):
        second_snapshot = self.store.put(
            source_code="TEST",
            source_url="https://example.test/call/2",
            content=b'{"title":"Second"}',
            mime_type="application/json",
            retrieved_at=self.at + timedelta(minutes=1),
        )
        first = self.grant()
        second = replace(
            first,
            source_external_id="call-2",
            source_url=second_snapshot.source_url,
            content_hash=second_snapshot.sha256,
            grant_call_id="grant:test:call-2",
            grant_version_id="legacy-unused-id-2",
            canonical_slug=first.canonical_slug,
            title="Second",
        )

        with self.assertRaises(CanonicalPublicationError):
            publish_grants_to_local_d1(
                [first, second],
                raw_dir=self.raw_dir,
                persist_root=self.persist,
                adapter_version="test-adapter-1.0",
                now=self.at,
            )

        connection = sqlite3.connect(self.database)
        try:
            for table in (
                "grant_calls",
                "grant_call_versions",
                "canonical_staging_items",
                "source_records",
                "document_versions",
                "grant_search_documents",
                "outbox_events",
            ):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                self.assertEqual(count, 0, table)
            run = connection.execute(
                """SELECT status,error_count
                   FROM source_runs ORDER BY started_at DESC LIMIT 1"""
            ).fetchone()
            self.assertEqual(run, ("FAILED", 1))
        finally:
            connection.close()

    def test_discovery_rejects_database_before_identity_indexes(self):
        legacy_root = self.root / "legacy"
        legacy_root.mkdir()
        legacy_db = legacy_root / "legacy.sqlite"
        connection = sqlite3.connect(legacy_db)
        try:
            for path in sorted((ROOT / "migrations").glob("*.sql")):
                if path.name.startswith("0025_"):
                    break
                connection.executescript(path.read_text(encoding="utf-8"))
        finally:
            connection.close()

        with self.assertRaisesRegex(RuntimeError, "fully migrated"):
            discover_local_d1_database(legacy_root)

    def test_raw_snapshot_provenance_is_url_specific_for_identical_bytes(self):
        other_url = "https://example.test/call/2"
        second = self.store.put(
            source_code="TEST",
            source_url=other_url,
            content=b'{"title":"Trusted local refresh"}',
            mime_type="application/json",
            retrieved_at=self.at + timedelta(minutes=1),
        )
        self.assertEqual(second.sha256, self.snapshot.sha256)
        self.assertNotEqual(second.snapshot_id, self.snapshot.snapshot_id)
        self.assertEqual(
            self.store.load_by_snapshot_id(self.snapshot.snapshot_id).source_url,
            self.snapshot.source_url,
        )
        self.assertEqual(
            self.store.load_by_snapshot_id(second.snapshot_id).source_url,
            other_url,
        )
        first_loaded = self.store.load_by_sha256(
            source_code="TEST",
            sha256=self.snapshot.sha256,
            source_url=self.snapshot.source_url,
        )
        second_loaded = self.store.load_by_sha256(
            source_code="TEST",
            sha256=second.sha256,
            source_url=other_url,
        )
        self.assertEqual(first_loaded.source_url, self.snapshot.source_url)
        self.assertEqual(second_loaded.source_url, other_url)
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            self.store.load_by_sha256(
                source_code="TEST",
                sha256=self.snapshot.sha256,
            )

    def test_active_refresh_entrypoints_do_not_use_legacy_direct_sql_publisher(self):
        for relative in (
            "scripts/local_ingest_nsa.py",
            "scripts/local_ingest_dotaceeu.py",
            "scripts/local_ingest_eu_funding.py",
        ):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("render_import_sql", content, relative)
            self.assertIn("publish_grants_to_local_d1", content, relative)

        refresh = (ROOT / "scripts/local_refresh_data.mjs").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("applySql", refresh)
        self.assertNotIn("-import.sql", refresh)

    def test_missing_raw_snapshot_fails_before_canonical_publish(self):
        bad = self.grant()
        missing_hash = hashlib.sha256(b"missing").hexdigest()
        bad = replace(bad, content_hash=missing_hash)
        with self.assertRaises(FileNotFoundError):
            publish_grants_to_local_d1(
                [bad],
                raw_dir=self.raw_dir,
                persist_root=self.persist,
                adapter_version="test-adapter-1.0",
                now=self.at,
            )


if __name__ == "__main__":
    unittest.main()
