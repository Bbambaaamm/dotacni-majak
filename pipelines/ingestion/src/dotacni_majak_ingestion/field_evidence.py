"""FieldEvidence persistence with integrity validation.

Provides a repository that persists provenance references (``field_evidence``)
to the canonical D1-compatible schema.  Every write is guarded by explicit
integrity checks so that evidence references always point to an existing
immutable ``document_versions`` row and, optionally, a ``document_sections`` row
with a valid page range.

The module is deliberately stdlib-only (``sqlite3`` / ``dataclasses`` /
``enum``) so that it can be imported and tested without the full ingestion
dependency tree.  It is exported through the package ``__init__`` for
application-layer callers.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Any


class VerificationStatus(str, Enum):
    """Contract status for how an evidence record was obtained.

    Mirrors the CHECK constraint on ``field_evidence.verification_status``.
    """

    AUTO_EXTRACTED = "AUTO_EXTRACTED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class FieldEvidenceIntegrityError(ValueError):
    """Raised when an evidence record fails integrity validation.

    Integrity violations — missing FK reference, invalid page range, invalid
    confidence, unknown verification status — are surfaced as this typed
    error so upstream pipelines can route the record to quarantine or
    re-extraction without silent data loss or silent acceptance of garbage.
    """


@dataclass(frozen=True, slots=True)
class FieldEvidenceRecord:
    """A single provenance reference from a canonical field back to its
    source document/section/page.

    Field names and value domains match the D1 schema in
    ``migrations/0002_documents_provenance.sql`` and the JSON contract in
    ``schemas/v1/field-evidence.schema.json``.

    ``confidence_ppm`` is parts-per-million (0–1 000 000) to match the
    DB CHECK constraint.  Use :meth:`from_confidence` to convert from the
    0.0–1.0 float used in the JSON schema.
    """

    id: str
    entity_type: str
    entity_id: str
    field_path: str
    document_version_id: str
    verification_status: str
    created_at: str
    document_section_id: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    evidence_text: str | None = None
    extraction_method: str | None = None
    extractor_version: str | None = None
    confidence_ppm: int | None = None

    # -- construction helpers ------------------------------------------------

    @classmethod
    def from_confidence(
        cls,
        *args: Any,
        confidence: float | None = None,
        **kwargs: Any,
    ) -> FieldEvidenceRecord:
        """Build a record from a 0.0–1.0 confidence float.

        Accepts the same positional/keyword arguments as the dataclass
        constructor but additionally converts ``confidence`` (float) into
        ``confidence_ppm`` (integer ppm).  Raises ``ValueError`` if the
        float is outside [0.0, 1.0].
        """
        if confidence is not None:
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(
                    f"confidence must be in [0.0, 1.0], got {confidence}"
                )
            kwargs = {"confidence_ppm": int(round(confidence * 1_000_000)), **kwargs}
        return cls(*args, **kwargs)


class FieldEvidenceRepository:
    """SQLite/D1-compatible repository for ``field_evidence`` rows.

    Integrity is enforced at two layers:

    1. **Application-level validation** — page range, confidence, and
       verification-status are checked *before* the SQL statement so that
       callers receive a structured ``FieldEvidenceIntegrityError`` rather
       than an opaque database error.
    2. **Database-level constraints** — FK ``ON DELETE RESTRICT`` on
       ``document_version_id`` and ``ON DELETE SET NULL`` on
       ``document_section_id`` are enforced via ``PRAGMA foreign_keys = ON``.
    """

    MAX_CONFIDENCE_PPM = 1_000_000

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.row_factory = sqlite3.Row

    # -- validation ----------------------------------------------------------

    @classmethod
    def _validate_record(cls, record: FieldEvidenceRecord) -> None:
        """Validate all application-level invariants before persistence."""
        if not record.id:
            raise FieldEvidenceIntegrityError("evidence id must not be empty")
        if not record.entity_type:
            raise FieldEvidenceIntegrityError("entity_type must not be empty")
        if not record.entity_id:
            raise FieldEvidenceIntegrityError("entity_id must not be empty")
        if not record.field_path:
            raise FieldEvidenceIntegrityError("field_path must not be empty")
        if not record.document_version_id:
            raise FieldEvidenceIntegrityError(
                "document_version_id must not be empty"
            )

        # Page range: both must be present or absent, from >= 1, to >= from.
        if record.page_from is not None or record.page_to is not None:
            if record.page_from is None or record.page_to is None:
                raise FieldEvidenceIntegrityError(
                    "page_from and page_to must both be set or both be None"
                )
            if record.page_from < 1:
                raise FieldEvidenceIntegrityError(
                    f"page_from must be >= 1, got {record.page_from}"
                )
            if record.page_to < record.page_from:
                raise FieldEvidenceIntegrityError(
                    f"page_to ({record.page_to}) must be >= "
                    f"page_from ({record.page_from})"
                )

        # Confidence: parts-per-million in [0, 1_000_000].
        if record.confidence_ppm is not None:
            if not 0 <= record.confidence_ppm <= cls.MAX_CONFIDENCE_PPM:
                raise FieldEvidenceIntegrityError(
                    f"confidence_ppm must be in [0, {cls.MAX_CONFIDENCE_PPM}], "
                    f"got {record.confidence_ppm}"
                )

        # Verification status must be one of the known enum values.
        if record.verification_status not in _VERIFICATION_VALUES:
            allowed = sorted(_VERIFICATION_VALUES)
            raise FieldEvidenceIntegrityError(
                f"unknown verification_status: {record.verification_status!r}; "
                f"expected one of {allowed}"
            )

    def _check_fk_references(self, record: FieldEvidenceRecord) -> None:
        """Verify that referenced immutable documents/sections exist.

        This is a defensive check; the DB FK constraint provides the
        authoritative guarantee.  Doing the check here yields a clear
        ``FieldEvidenceIntegrityError`` message instead of an opaque
        ``IntegrityError``.
        """
        version = self.connection.execute(
            "SELECT 1 FROM document_versions WHERE id = ?",
            (record.document_version_id,),
        ).fetchone()
        if version is None:
            raise FieldEvidenceIntegrityError(
                f"document_version_id {record.document_version_id!r} does not "
                "reference an existing document version"
            )

        if record.document_section_id is not None:
            section = self.connection.execute(
                "SELECT 1 FROM document_sections WHERE id = ?",
                (record.document_section_id,),
            ).fetchone()
            if section is None:
                raise FieldEvidenceIntegrityError(
                    f"document_section_id {record.document_section_id!r} does "
                    "not reference an existing document section"
                )

    # -- persistence ---------------------------------------------------------

    def save(self, record: FieldEvidenceRecord) -> None:
        """Persist *record* with idempotent retry semantics.

        Uses ``INSERT … ON CONFLICT(id) DO UPDATE`` so that retrying the
        same evidence (same ``id``) is a safe no-op that refreshes mutable
        metadata fields without creating duplicates.
        """
        self._validate_record(record)
        self._check_fk_references(record)

        self.connection.execute(
            """
            INSERT INTO field_evidence (
                id, entity_type, entity_id, field_path,
                document_version_id, document_section_id,
                page_from, page_to, evidence_text,
                extraction_method, extractor_version,
                confidence_ppm, verification_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                verification_status = excluded.verification_status,
                confidence_ppm  = excluded.confidence_ppm,
                page_from       = excluded.page_from,
                page_to         = excluded.page_to,
                evidence_text   = excluded.evidence_text,
                extraction_method    = excluded.extraction_method,
                extractor_version    = excluded.extractor_version,
                document_version_id  = excluded.document_version_id,
                document_section_id  = excluded.document_section_id
            """,
            (
                record.id,
                record.entity_type,
                record.entity_id,
                record.field_path,
                record.document_version_id,
                record.document_section_id,
                record.page_from,
                record.page_to,
                record.evidence_text,
                record.extraction_method,
                record.extractor_version,
                record.confidence_ppm,
                record.verification_status,
                record.created_at,
            ),
        )
        self.connection.commit()

    # -- queries -------------------------------------------------------------

    _SELECT_COLUMNS = (
        "id, entity_type, entity_id, field_path, "
        "document_version_id, document_section_id, "
        "page_from, page_to, evidence_text, "
        "extraction_method, extractor_version, "
        "confidence_ppm, verification_status, created_at"
    )

    def find_by_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> list[FieldEvidenceRecord]:
        """Return all evidence rows for *entity_id*, newest first."""
        rows = self.connection.execute(
            f"""
            SELECT {self._SELECT_COLUMNS}
            FROM field_evidence
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY created_at DESC, id ASC
            """,
            (entity_type, entity_id),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def find_by_field(
        self,
        entity_type: str,
        entity_id: str,
        field_path: str,
    ) -> list[FieldEvidenceRecord]:
        """Return evidence rows for a specific *field_path* on *entity_id*."""
        rows = self.connection.execute(
            f"""
            SELECT {self._SELECT_COLUMNS}
            FROM field_evidence
            WHERE entity_type = ? AND entity_id = ? AND field_path = ?
            ORDER BY created_at DESC, id ASC
            """,
            (entity_type, entity_id, field_path),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _from_row(row: sqlite3.Row) -> FieldEvidenceRecord:
        return FieldEvidenceRecord(
            id=row["id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            field_path=row["field_path"],
            document_version_id=row["document_version_id"],
            document_section_id=row["document_section_id"],
            page_from=row["page_from"],
            page_to=row["page_to"],
            evidence_text=row["evidence_text"],
            extraction_method=row["extraction_method"],
            extractor_version=row["extractor_version"],
            confidence_ppm=row["confidence_ppm"],
            verification_status=row["verification_status"],
            created_at=row["created_at"],
        )


# Pre-computed set of valid verification status strings for fast lookup.
_VERIFICATION_VALUES = frozenset(item.value for item in VerificationStatus)
