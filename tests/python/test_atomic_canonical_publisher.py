import hashlib
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "ingestion" / "src"))

from dotacni_majak_ingestion.canonical_publisher import (
    CanonicalPublicationError,
    PublicationErrorCode,
    SqliteCanonicalPublisher,
)
from dotacni_majak_ingestion.staging import (
    SqliteCanonicalStagingRepository,
    StagingProvenanceStatus,
    StagingState,
    StagingValidationStatus,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AtomicCanonicalPublisherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.connection.executescript(path.read_text(encoding="utf-8"))

        self.connection.execute(
            "INSERT INTO providers(id,name,provider_type) "
            "VALUES ('provider','Provider','NATIONAL')"
        )
        self.connection.execute(
            """INSERT INTO programmes(
                 id,provider_id,name,funding_origin
               ) VALUES ('programme','provider','Programme','CZ_NATIONAL')"""
        )
        self.connection.execute(
            """INSERT INTO source_registry(
                 id,code,name,base_url,adapter_key,authority,retrieval_mode,
                 refresh_minutes,enabled,priority
               ) VALUES (
                 'source','TEST','Test source','https://example.test/',
                 'test','OFFICIAL','HTML',60,1,10
               )"""
        )
        self.connection.execute(
            """INSERT INTO source_documents(
                 id,source_id,document_type,title,source_url,first_seen_at,last_seen_at
               ) VALUES (
                 'doc-1','source','CALL_DOCUMENT','Call',
                 'https://example.test/call.pdf',
                 '2026-09-26T18:00:00+00:00',
                 '2026-09-26T18:00:00+00:00'
               )"""
        )
        self.connection.execute(
            """INSERT INTO document_versions(
                 id,source_document_id,sha256,retrieved_at,mime_type,
                 file_size,object_key,extraction_status
               ) VALUES (
                 'dv-1','doc-1',?,
                 '2026-09-26T18:00:00+00:00','application/pdf',
                 12,'raw/TEST/a.pdf','EXTRACTED'
               )""",
            (digest("document"),),
        )
        self.connection.commit()
        self.staging = SqliteCanonicalStagingRepository(self.connection)
        self.publisher = SqliteCanonicalPublisher(self.connection)
        self.now = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)

    def _payload(self, *, title="Grant", evidence_version="dv-1"):
        return {
            "programme_id": "programme",
            "canonical_slug": "test-grant",
            "canonical_code": "CALL-1",
            "title": title,
            "summary": "Sportovní infrastruktura",
            "status": "OPEN",
            "verification_status": "AUTO_EXTRACTED",
            "captured_at": "2026-09-26T19:00:00+00:00",
            "submission_close_at": "2026-12-31T23:59:59+00:00",
            "official_detail_url": "https://example.test/call/1",
            "currency_code": "CZK",
            "normalization_version": "test-v1",
            "evidence": [
                {
                    "field_path": "/title",
                    "document_version_id": evidence_version,
                    "verification_status": "AUTO_EXTRACTED",
                    "page_from": 1,
                    "page_to": 1,
                    "evidence_text": title,
                    "extraction_method": "PDF_TEXT",
                    "extractor_version": "test",
                    "confidence_ppm": 990000,
                }
            ],
        }

    def _ready_candidate(self, *, content="v1", payload=None):
        content_hash = digest(content)
        self.connection.execute(
            """INSERT INTO source_records(
                 id,source_id,external_id,canonical_url,record_type,
                 grant_call_id,first_seen_at,last_seen_at,presence_state,
                 missing_run_count,content_hash
               ) VALUES (
                 'source:call-1','source','call-1',
                 'https://example.test/call/1','GRANT_CALL',NULL,
                 '2026-09-26T18:00:00+00:00',
                 '2026-09-26T19:00:00+00:00','SEEN',0,?
               )
               ON CONFLICT(source_id,external_id) DO UPDATE SET
                 content_hash=excluded.content_hash,
                 last_seen_at=excluded.last_seen_at""",
            (content_hash,),
        )
        self.connection.commit()
        candidate = self.staging.stage(
            source_code="TEST",
            external_id="call-1",
            entity_type="GRANT_CALL",
            canonical_identity="grant:test:call-1",
            payload=payload or self._payload(),
            content_hash=content_hash,
            provenance_status=StagingProvenanceStatus.COMPLETE,
            now=self.now,
        )
        return self.staging.mark_validation(
            candidate.id,
            StagingValidationStatus.VALID,
            now=self.now,
        )

    def test_publish_is_atomic_and_links_all_trust_chain_parts(self):
        candidate = self._ready_candidate()
        result = self.publisher.publish(candidate.id, now=self.now)

        self.assertTrue(result.created_version)
        self.assertEqual(result.version_number, 1)
        self.assertEqual(result.evidence_count, 1)
        self.assertEqual(result.outbox_event_count, 2)

        call = self.connection.execute(
            """SELECT current_version_id,current_status,current_title
               FROM grant_calls WHERE id=?""",
            (result.grant_call_id,),
        ).fetchone()
        self.assertEqual(
            tuple(call),
            (result.grant_call_version_id, "OPEN", "Grant"),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM field_evidence WHERE entity_id=?",
                (result.grant_call_version_id,),
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE aggregate_id=?",
                (result.grant_call_id,),
            ).fetchone()[0],
            2,
        )
        source_link = self.connection.execute(
            "SELECT grant_call_id FROM source_records WHERE id='source:call-1'"
        ).fetchone()[0]
        self.assertEqual(source_link, result.grant_call_id)
        staged = self.staging.get(candidate.id)
        self.assertEqual(staged.state, StagingState.PUBLISHED)
        self.assertEqual(
            staged.published_entity_id,
            result.grant_call_version_id,
        )

    def test_retry_of_published_candidate_is_idempotent(self):
        candidate = self._ready_candidate()
        first = self.publisher.publish(candidate.id, now=self.now)
        second = self.publisher.publish(candidate.id, now=self.now)
        self.assertEqual(
            first.grant_call_version_id,
            second.grant_call_version_id,
        )
        self.assertFalse(second.created_version)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM grant_call_versions"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM outbox_events"
            ).fetchone()[0],
            2,
        )

    def test_changed_content_creates_next_immutable_version(self):
        first_candidate = self._ready_candidate(content="v1")
        first = self.publisher.publish(first_candidate.id, now=self.now)

        second_payload = self._payload(title="Grant changed")
        second_candidate = self._ready_candidate(
            content="v2",
            payload=second_payload,
        )
        second = self.publisher.publish(
            second_candidate.id,
            now=datetime(2026, 9, 26, 21, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(first.version_number, 1)
        self.assertEqual(second.version_number, 2)
        self.assertNotEqual(
            first.grant_call_version_id,
            second.grant_call_version_id,
        )
        versions = self.connection.execute(
            """SELECT version_number,title FROM grant_call_versions
               ORDER BY version_number"""
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in versions],
            [(1, "Grant"), (2, "Grant changed")],
        )

    def test_invalid_evidence_rolls_back_every_canonical_write(self):
        candidate = self._ready_candidate(
            payload=self._payload(evidence_version="missing-dv")
        )
        with self.assertRaises(CanonicalPublicationError) as caught:
            self.publisher.publish(candidate.id, now=self.now)
        self.assertEqual(caught.exception.code, PublicationErrorCode.EVIDENCE_INVALID)

        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM grant_calls").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM grant_call_versions"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM field_evidence").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0],
            0,
        )
        self.assertEqual(self.staging.get(candidate.id).state, StagingState.READY)

    def test_outbox_failure_rolls_back_version_evidence_link_and_staging(self):
        candidate = self._ready_candidate()
        self.connection.execute(
            """CREATE TRIGGER fail_outbox
               BEFORE INSERT ON outbox_events
               BEGIN
                 SELECT RAISE(ABORT, 'forced outbox failure');
               END"""
        )
        self.connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.publisher.publish(candidate.id, now=self.now)

        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM grant_calls").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM field_evidence").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0],
            0,
        )
        self.assertIsNone(
            self.connection.execute(
                "SELECT grant_call_id FROM source_records WHERE id='source:call-1'"
            ).fetchone()[0]
        )
        self.assertEqual(self.staging.get(candidate.id).state, StagingState.READY)

    def test_source_hash_mismatch_fails_before_transaction(self):
        candidate = self._ready_candidate()
        self.connection.execute(
            "UPDATE source_records SET content_hash=? WHERE id='source:call-1'",
            (digest("newer-upstream"),),
        )
        self.connection.commit()

        with self.assertRaises(CanonicalPublicationError) as caught:
            self.publisher.publish(candidate.id, now=self.now)
        self.assertEqual(
            caught.exception.code,
            PublicationErrorCode.SOURCE_RECORD_MISMATCH,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM grant_calls").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
