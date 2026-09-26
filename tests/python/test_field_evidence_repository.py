"""Integration tests for the FieldEvidence persistence repository.

Tests run against an in-memory SQLite database with the full migration chain
applied, exercising DB-level FK constraints (ON DELETE RESTRICT / SET NULL),
application-level integrity checks (page range, confidence, verification
status), idempotent upsert semantics, and entity/field queries.

The ``field_evidence`` module is loaded via ``importlib`` so that the test
suite remains dependency-free (stdlib only) even when the broader ingestion
package requires pydantic/httpx for other modules.
"""

import importlib.util
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = (
        ROOT
        / "pipelines"
        / "ingestion"
        / "src"
        / "dotacni_majak_ingestion"
        / "field_evidence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "field_evidence_under_test", path
    )
    if spec is None:
        raise ImportError(f"cannot create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    import sys as _sys

    _sys.modules["field_evidence_under_test"] = module
    spec.loader.exec_module(module)
    return module


_fe = _load_module()
FieldEvidenceRecord = _fe.FieldEvidenceRecord
FieldEvidenceRepository = _fe.FieldEvidenceRepository
FieldEvidenceIntegrityError = _fe.FieldEvidenceIntegrityError
VerificationStatus = _fe.VerificationStatus


def _migrate():
    """Apply every migration in order to a fresh in-memory SQLite DB."""
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


def _seed_prerequisites(connection):
    """Insert the FK dependency chain: source_registry → source_documents
    → document_versions → document_sections."""
    connection.execute(
        "INSERT INTO source_registry(id, code, name, base_url, "
        "adapter_key, authority, retrieval_mode, refresh_minutes) "
        "VALUES ('src-1', 'TESTSRC', 'Test Source', "
        "'https://test.example.com/', 'test', 'OFFICIAL', 'API', 240)"
    )
    connection.execute(
        "INSERT INTO source_documents(id, source_id, document_type, "
        "source_url, first_seen_at) "
        "VALUES ('doc-1', 'src-1', 'CALL_DOCUMENT', "
        "'https://test.example.com/doc/1', '2026-01-01T00:00:00Z')"
    )
    sha = "a" * 64
    connection.execute(
        "INSERT INTO document_versions(id, source_document_id, sha256, "
        "retrieved_at, mime_type, object_key, extraction_status) "
        f"VALUES ('dv-1', 'doc-1', '{sha}', '2026-01-01T00:00:00Z', "
        f"'application/pdf', 'raw/test/{sha}.bin', 'EXTRACTED')"
    )
    connection.execute(
        "INSERT INTO document_sections(id, document_version_id, "
        "page_from, page_to, text_content) "
        "VALUES ('sec-1', 'dv-1', 1, 5, 'Section text content')"
    )
    connection.commit()


def _make_evidence(**overrides):
    defaults = dict(
        id="ev-1",
        entity_type="GRANT_CALL",
        entity_id="grant-1",
        field_path="submission_close_at",
        document_version_id="dv-1",
        document_section_id="sec-1",
        page_from=2,
        page_to=3,
        evidence_text="Deadline: 30.09.2026",
        extraction_method="pdf_ocr",
        extractor_version="1.0.0",
        confidence_ppm=850_000,
        verification_status="PARTIALLY_VERIFIED",
        created_at="2026-09-23T10:00:00Z",
    )
    defaults.update(overrides)
    return FieldEvidenceRecord(**defaults)


class FieldEvidenceRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.connection = _migrate()
        _seed_prerequisites(self.connection)
        self.repo = FieldEvidenceRepository(self.connection)

    def tearDown(self):
        self.connection.close()

    # -- save / persistence --------------------------------------------------

    def test_save_valid_evidence_persists_all_fields(self):
        self.repo.save(_make_evidence())
        row = self.connection.execute(
            "SELECT id, entity_type, entity_id, field_path, "
            "document_version_id, document_section_id, "
            "page_from, page_to, evidence_text, extraction_method, "
            "extractor_version, confidence_ppm, verification_status, "
            "created_at FROM field_evidence WHERE id = ?",
            ("ev-1",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["entity_type"], "GRANT_CALL")
        self.assertEqual(row["entity_id"], "grant-1")
        self.assertEqual(row["field_path"], "submission_close_at")
        self.assertEqual(row["document_version_id"], "dv-1")
        self.assertEqual(row["document_section_id"], "sec-1")
        self.assertEqual(row["page_from"], 2)
        self.assertEqual(row["page_to"], 3)
        self.assertEqual(row["evidence_text"], "Deadline: 30.09.2026")
        self.assertEqual(row["extraction_method"], "pdf_ocr")
        self.assertEqual(row["extractor_version"], "1.0.0")
        self.assertEqual(row["confidence_ppm"], 850_000)
        self.assertEqual(row["verification_status"], "PARTIALLY_VERIFIED")
        self.assertEqual(row["created_at"], "2026-09-23T10:00:00Z")

    def test_save_idempotent_retry_updates_not_duplicates(self):
        """Retrying the same evidence id must be a safe upsert."""
        self.repo.save(_make_evidence())
        updated = _make_evidence(
            verification_status="VERIFIED",
            confidence_ppm=950_000,
        )
        self.repo.save(updated)
        count = self.connection.execute(
            "SELECT COUNT(*) FROM field_evidence WHERE id = ?", ("ev-1",)
        ).fetchone()[0]
        self.assertEqual(count, 1)
        row = self.connection.execute(
            "SELECT verification_status, confidence_ppm "
            "FROM field_evidence WHERE id = ?",
            ("ev-1",),
        ).fetchone()
        self.assertEqual(row["verification_status"], "VERIFIED")
        self.assertEqual(row["confidence_ppm"], 950_000)

    # -- integrity: FK references --------------------------------------------

    def test_save_rejects_nonexistent_document_version(self):
        record = _make_evidence(document_version_id="no-such-version")
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("document version", str(ctx.exception))
        count = self.connection.execute(
            "SELECT COUNT(*) FROM field_evidence"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_save_rejects_nonexistent_document_section(self):
        record = _make_evidence(document_section_id="no-such-section")
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("document section", str(ctx.exception))

    # -- integrity: page range ------------------------------------------------

    def test_save_rejects_page_to_less_than_page_from(self):
        record = _make_evidence(page_from=5, page_to=3)
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("page_to", str(ctx.exception))

    def test_save_rejects_page_from_below_one(self):
        record = _make_evidence(page_from=0, page_to=2)
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("page_from", str(ctx.exception))

    def test_save_rejects_partial_page_range(self):
        record = _make_evidence(page_from=None, page_to=5)
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("both", str(ctx.exception))

    def test_save_accepts_null_page_range(self):
        record = _make_evidence(page_from=None, page_to=None)
        self.repo.save(record)
        row = self.connection.execute(
            "SELECT page_from, page_to FROM field_evidence WHERE id = ?",
            ("ev-1",),
        ).fetchone()
        self.assertIsNone(row["page_from"])
        self.assertIsNone(row["page_to"])

    def test_save_accepts_equal_page_from_and_to(self):
        record = _make_evidence(page_from=4, page_to=4)
        self.repo.save(record)
        row = self.connection.execute(
            "SELECT page_from, page_to FROM field_evidence WHERE id = ?",
            ("ev-1",),
        ).fetchone()
        self.assertEqual(row["page_from"], 4)
        self.assertEqual(row["page_to"], 4)

    # -- integrity: confidence ------------------------------------------------

    def test_save_rejects_confidence_above_max(self):
        record = _make_evidence(confidence_ppm=1_000_001)
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("confidence_ppm", str(ctx.exception))

    def test_save_rejects_negative_confidence(self):
        record = _make_evidence(confidence_ppm=-1)
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("confidence_ppm", str(ctx.exception))

    def test_save_accepts_null_confidence(self):
        record = _make_evidence(confidence_ppm=None)
        self.repo.save(record)
        row = self.connection.execute(
            "SELECT confidence_ppm FROM field_evidence WHERE id = ?",
            ("ev-1",),
        ).fetchone()
        self.assertIsNone(row["confidence_ppm"])

    def test_save_accepts_boundary_confidence(self):
        self.repo.save(_make_evidence(id="ev-lo", confidence_ppm=0))
        self.repo.save(_make_evidence(id="ev-hi", confidence_ppm=1_000_000))
        count = self.connection.execute(
            "SELECT COUNT(*) FROM field_evidence"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    # -- integrity: verification status ---------------------------------------

    def test_all_verification_statuses_accepted(self):
        for status in VerificationStatus:
            self.repo.save(
                _make_evidence(id=f"ev-{status.value}", verification_status=status.value)
            )
        count = self.connection.execute(
            "SELECT COUNT(*) FROM field_evidence"
        ).fetchone()[0]
        self.assertEqual(count, len(list(VerificationStatus)))

    def test_save_rejects_unknown_verification_status(self):
        """UNKNOWN/error state must be part of the explicit contract,
        not silently accepted as a valid status."""
        record = _make_evidence(verification_status="SOMETHING_WEIRD")
        with self.assertRaises(FieldEvidenceIntegrityError) as ctx:
            self.repo.save(record)
        self.assertIn("verification_status", str(ctx.exception))

    # -- from_confidence helper -----------------------------------------------

    def test_from_confidence_converts_float_to_ppm(self):
        record = FieldEvidenceRecord.from_confidence(
            id="ev-conf",
            entity_type="GRANT_CALL",
            entity_id="grant-1",
            field_path="eligibility",
            document_version_id="dv-1",
            verification_status="AUTO_EXTRACTED",
            created_at="2026-09-23T10:00:00Z",
            confidence=0.5,
        )
        self.assertEqual(record.confidence_ppm, 500_000)
        self.repo.save(record)
        row = self.connection.execute(
            "SELECT confidence_ppm FROM field_evidence WHERE id = ?",
            ("ev-conf",),
        ).fetchone()
        self.assertEqual(row["confidence_ppm"], 500_000)

    def test_from_confidence_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            FieldEvidenceRecord.from_confidence(
                id="ev-bad",
                entity_type="GRANT_CALL",
                entity_id="grant-1",
                field_path="x",
                document_version_id="dv-1",
                verification_status="AUTO_EXTRACTED",
                created_at="2026-09-23T10:00:00Z",
                confidence=1.5,
            )

    # -- queries --------------------------------------------------------------

    def test_find_by_entity_returns_matching_records(self):
        self.repo.save(_make_evidence(id="ev-a", entity_id="grant-1"))
        self.repo.save(_make_evidence(id="ev-b", entity_id="grant-1"))
        self.repo.save(_make_evidence(id="ev-c", entity_id="grant-2"))
        results = self.repo.find_by_entity("GRANT_CALL", "grant-1")
        ids = sorted(r.id for r in results)
        self.assertEqual(ids, ["ev-a", "ev-b"])

    def test_find_by_field_filters_by_field_path(self):
        self.repo.save(_make_evidence(id="ev-a", field_path="submission_close_at"))
        self.repo.save(_make_evidence(id="ev-b", field_path="eligibility"))
        results = self.repo.find_by_field(
            "GRANT_CALL", "grant-1", "submission_close_at"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "ev-a")

    def test_find_by_entity_empty_for_unknown_entity(self):
        results = self.repo.find_by_entity("GRANT_CALL", "nonexistent")
        self.assertEqual(results, [])

    def test_find_by_entity_ordered_by_created_at_desc(self):
        self.repo.save(
            _make_evidence(id="ev-older", created_at="2026-01-01T00:00:00Z")
        )
        self.repo.save(
            _make_evidence(id="ev-newer", created_at="2026-09-01T00:00:00Z")
        )
        results = self.repo.find_by_entity("GRANT_CALL", "grant-1")
        self.assertEqual(results[0].id, "ev-newer")
        self.assertEqual(results[1].id, "ev-older")

    # -- FK deletion restrictions ---------------------------------------------

    def test_document_version_delete_restricted_when_evidence_references_it(self):
        """document_version_id ON DELETE RESTRICT must block deletion."""
        self.repo.save(_make_evidence())
        try:
            self.connection.execute(
                "DELETE FROM document_versions WHERE id = ?", ("dv-1",)
            )
        except sqlite3.IntegrityError:
            self.connection.rollback()
        else:
            self.fail("Expected sqlite3.IntegrityError for ON DELETE RESTRICT")
        # Evidence must still exist.
        count = self.connection.execute(
            "SELECT COUNT(*) FROM field_evidence"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_document_section_delete_sets_section_id_null(self):
        """document_section_id ON DELETE SET NULL must nullify the reference."""
        self.repo.save(_make_evidence())
        self.connection.execute(
            "DELETE FROM document_sections WHERE id = ?", ("sec-1",)
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT document_section_id FROM field_evidence WHERE id = ?",
            ("ev-1",),
        ).fetchone()
        self.assertIsNone(row["document_section_id"])

    def test_document_version_delete_allowed_after_evidence_removed(self):
        """Removing evidence first must unblock the restricted deletion."""
        self.repo.save(_make_evidence())
        self.connection.execute(
            "DELETE FROM field_evidence WHERE id = ?", ("ev-1",)
        )
        self.connection.commit()
        # Now deletion of the document version should succeed.
        self.connection.execute(
            "DELETE FROM document_versions WHERE id = ?", ("dv-1",)
        )
        self.connection.commit()
        count = self.connection.execute(
            "SELECT COUNT(*) FROM document_versions WHERE id = ?", ("dv-1",)
        ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
