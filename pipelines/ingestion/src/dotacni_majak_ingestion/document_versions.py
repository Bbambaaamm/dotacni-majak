from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from enum import Enum

from .snapshot import RawSnapshot


_ALLOWED_DOCUMENT_TYPES = {
    "CALL_DOCUMENT",
    "GUIDELINES",
    "ANNEX",
    "APPLICATION_FORM",
    "FAQ",
    "PROGRAMME_DOCUMENT",
    "OTHER",
}
_ALLOWED_EXTRACTION = {"PENDING", "EXTRACTED", "FAILED", "QUARANTINED"}


class DocumentVersionChange(str, Enum):
    NEW_DOCUMENT = "NEW_DOCUMENT"
    NEW_VERSION = "NEW_VERSION"
    NOT_MODIFIED = "NOT_MODIFIED"


@dataclass(frozen=True, slots=True)
class DocumentVersionObservation:
    source_document_id: str
    document_version_id: str
    source_code: str
    document_type: str
    source_url: str
    sha256: str
    retrieved_at: str
    mime_type: str
    object_key: str
    extraction_status: str
    change: DocumentVersionChange
    grant_call_id: str | None
    title: str | None


class SqliteDocumentVersionRepository:
    """Stable SourceDocument identity + immutable content versions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")

    def _source_id(self, source_code: str) -> str:
        row = self.connection.execute(
            "SELECT id FROM source_registry WHERE code = ?",
            (source_code,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown source_code {source_code!r}")
        return str(row[0])

    @staticmethod
    def _document_id(
        source_id: str,
        document_type: str,
        source_url: str,
    ) -> str:
        digest = hashlib.sha256(
            "\x1f".join((source_id, document_type, source_url)).encode("utf-8")
        ).hexdigest()
        return "doc_" + digest[:40]

    @staticmethod
    def _version_id(source_document_id: str, sha256: str) -> str:
        return "dv_" + hashlib.sha256(
            (source_document_id + "\x1f" + sha256).encode("utf-8")
        ).hexdigest()[:40]

    def _version_row(
        self,
        source_document_id: str,
        sha256: str,
    ) -> tuple[object, ...] | None:
        return self.connection.execute(
            """SELECT
                 dv.id, dv.retrieved_at, dv.mime_type, dv.object_key,
                 dv.extraction_status, sd.grant_call_id, sd.title,
                 sd.source_url, sd.document_type
               FROM document_versions dv
               JOIN source_documents sd ON sd.id = dv.source_document_id
               WHERE dv.source_document_id = ? AND dv.sha256 = ?""",
            (source_document_id, sha256),
        ).fetchone()

    def observe_snapshot(
        self,
        *,
        source_code: str,
        document_type: str,
        snapshot: RawSnapshot,
        grant_call_id: str | None = None,
        title: str | None = None,
        parser_version: str | None = None,
        extraction_status: str = "PENDING",
        page_count: int | None = None,
        language_code: str | None = None,
    ) -> DocumentVersionObservation:
        if document_type not in _ALLOWED_DOCUMENT_TYPES:
            raise ValueError("unsupported document_type")
        if extraction_status not in _ALLOWED_EXTRACTION:
            raise ValueError("unsupported extraction_status")
        if snapshot.source_code != source_code:
            raise ValueError("snapshot source_code does not match repository source")
        if page_count is not None and page_count < 0:
            raise ValueError("page_count must be >= 0")

        source_id = self._source_id(source_code)
        source_document_id = self._document_id(
            source_id, document_type, snapshot.source_url
        )

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing_document = self.connection.execute(
                """SELECT id, grant_call_id, title
                   FROM source_documents
                   WHERE source_id=? AND document_type=? AND source_url=?""",
                (source_id, document_type, snapshot.source_url),
            ).fetchone()

            new_document = existing_document is None
            if new_document:
                self.connection.execute(
                    """INSERT INTO source_documents(
                         id, grant_call_id, source_id, document_type, title,
                         source_url, first_seen_at, last_seen_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        source_document_id,
                        grant_call_id,
                        source_id,
                        document_type,
                        title,
                        snapshot.source_url,
                        snapshot.retrieved_at,
                        snapshot.retrieved_at,
                    ),
                )
            else:
                source_document_id = str(existing_document[0])
                linked_grant = (
                    grant_call_id
                    if grant_call_id is not None
                    else existing_document[1]
                )
                effective_title = (
                    title if title is not None else existing_document[2]
                )
                self.connection.execute(
                    """UPDATE source_documents
                       SET grant_call_id=?, title=?, last_seen_at=?
                       WHERE id=?""",
                    (
                        linked_grant,
                        effective_title,
                        snapshot.retrieved_at,
                        source_document_id,
                    ),
                )

            existing_version = self._version_row(
                source_document_id, snapshot.sha256
            )
            if existing_version is None:
                document_version_id = self._version_id(
                    source_document_id, snapshot.sha256
                )
                self.connection.execute(
                    """INSERT INTO document_versions(
                         id, source_document_id, sha256, retrieved_at,
                         mime_type, file_size, object_key, parser_version,
                         extraction_status, page_count, language_code
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        document_version_id,
                        source_document_id,
                        snapshot.sha256,
                        snapshot.retrieved_at,
                        snapshot.mime_type,
                        snapshot.size_bytes,
                        snapshot.object_key,
                        parser_version,
                        extraction_status,
                        page_count,
                        language_code,
                    ),
                )
                change = (
                    DocumentVersionChange.NEW_DOCUMENT
                    if new_document
                    else DocumentVersionChange.NEW_VERSION
                )
            else:
                document_version_id = str(existing_version[0])
                change = DocumentVersionChange.NOT_MODIFIED

            row = self._version_row(source_document_id, snapshot.sha256)
            if row is None:
                raise RuntimeError("document version observation was not persisted")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        (
            version_id,
            retrieved_at,
            mime_type,
            object_key,
            stored_extraction_status,
            stored_grant_call_id,
            stored_title,
            source_url,
            stored_document_type,
        ) = row
        return DocumentVersionObservation(
            source_document_id=source_document_id,
            document_version_id=str(version_id),
            source_code=source_code,
            document_type=str(stored_document_type),
            source_url=str(source_url),
            sha256=snapshot.sha256,
            retrieved_at=str(retrieved_at),
            mime_type=str(mime_type),
            object_key=str(object_key),
            extraction_status=str(stored_extraction_status),
            change=change,
            grant_call_id=(
                str(stored_grant_call_id)
                if stored_grant_call_id is not None
                else None
            ),
            title=str(stored_title) if stored_title is not None else None,
        )

    def latest(
        self,
        source_document_id: str,
    ) -> DocumentVersionObservation | None:
        row = self.connection.execute(
            """SELECT
                 dv.id, s.code, sd.document_type, sd.source_url, dv.sha256,
                 dv.retrieved_at, dv.mime_type, dv.object_key,
                 dv.extraction_status, sd.grant_call_id, sd.title
               FROM document_versions dv
               JOIN source_documents sd ON sd.id=dv.source_document_id
               JOIN source_registry s ON s.id=sd.source_id
               WHERE dv.source_document_id=?
               ORDER BY dv.retrieved_at DESC, dv.id DESC
               LIMIT 1""",
            (source_document_id,),
        ).fetchone()
        if row is None:
            return None
        (
            version_id,
            source_code,
            document_type,
            source_url,
            sha256,
            retrieved_at,
            mime_type,
            object_key,
            extraction_status,
            grant_call_id,
            title,
        ) = row
        return DocumentVersionObservation(
            source_document_id=source_document_id,
            document_version_id=str(version_id),
            source_code=str(source_code),
            document_type=str(document_type),
            source_url=str(source_url),
            sha256=str(sha256),
            retrieved_at=str(retrieved_at),
            mime_type=str(mime_type),
            object_key=str(object_key),
            extraction_status=str(extraction_status),
            change=DocumentVersionChange.NOT_MODIFIED,
            grant_call_id=(
                str(grant_call_id) if grant_call_id is not None else None
            ),
            title=str(title) if title is not None else None,
        )
