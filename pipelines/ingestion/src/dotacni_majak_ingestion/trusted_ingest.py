from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .canonical_publisher import GrantPublicationResult, SqliteCanonicalPublisher
from .document_versions import (
    DocumentVersionObservation,
    SqliteDocumentVersionRepository,
)
from .local_publish import SearchableGrant
from .snapshot import RawSnapshot
from .source_records import SourceRecordObservation, SqliteSourceRecordRepository
from .staging import (
    SqliteCanonicalStagingRepository,
    StagingProvenanceStatus,
    StagingValidationStatus,
)


@dataclass(frozen=True, slots=True)
class TrustedGrantIngestResult:
    source_record: SourceRecordObservation
    document_version: DocumentVersionObservation
    publication: GrantPublicationResult


class TrustedGrantIngestor:
    """Bridge normalized connector output into the trusted canonical pipeline."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.source_records = SqliteSourceRecordRepository(connection)
        self.documents = SqliteDocumentVersionRepository(connection)
        self.staging = SqliteCanonicalStagingRepository(connection)
        self.publisher = SqliteCanonicalPublisher(connection)

    def _upsert_catalog(
        self,
        grant: SearchableGrant,
        *,
        commit: bool = True,
    ) -> None:
        if commit:
            self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """INSERT INTO providers(
                     id,name,provider_type,official_url
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     provider_type=excluded.provider_type,
                     official_url=excluded.official_url""",
                (
                    grant.provider_id,
                    grant.provider_name,
                    grant.provider_type,
                    grant.source_base_url,
                ),
            )
            self.connection.execute(
                """INSERT INTO programmes(
                     id,provider_id,name,funding_origin,official_url
                   ) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     provider_id=excluded.provider_id,
                     name=excluded.name,
                     funding_origin=excluded.funding_origin,
                     official_url=excluded.official_url""",
                (
                    grant.programme_id,
                    grant.provider_id,
                    grant.programme_name,
                    grant.funding_origin,
                    grant.source_base_url,
                ),
            )
            self.connection.execute(
                """INSERT INTO source_registry(
                     id,code,name,base_url,adapter_key,authority,retrieval_mode,
                     refresh_minutes,enabled,priority
                   ) VALUES (?, ?, ?, ?, ?, 'OFFICIAL', ?, 360, 1, 10)
                   ON CONFLICT(id) DO UPDATE SET
                     code=excluded.code,
                     name=excluded.name,
                     base_url=excluded.base_url,
                     adapter_key=excluded.adapter_key,
                     retrieval_mode=excluded.retrieval_mode,
                     enabled=1""",
                (
                    grant.source_id,
                    grant.source_code,
                    grant.source_name,
                    grant.source_base_url,
                    grant.adapter_key,
                    grant.retrieval_mode,
                ),
            )
            if commit:
                self.connection.commit()
        except Exception:
            if commit:
                self.connection.rollback()
            raise

    def ingest(
        self,
        grant: SearchableGrant,
        *,
        record_snapshot: RawSnapshot,
        now: datetime | None = None,
        source_run_id: str | None = None,
        commit: bool = True,
    ) -> TrustedGrantIngestResult:
        grant.validate()
        if record_snapshot.source_code != grant.source_code:
            raise ValueError("RAW snapshot source does not match normalized grant")
        if record_snapshot.sha256 != grant.content_hash:
            raise ValueError("RAW snapshot hash does not match normalized grant")

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        current = current.astimezone(timezone.utc)

        self._upsert_catalog(grant, commit=commit)
        source_record = self.source_records.observe(
            source_code=grant.source_code,
            external_id=grant.source_external_id,
            canonical_url=grant.source_url,
            record_type="GRANT_CALL",
            content_hash=grant.content_hash,
            now=current,
            commit=commit,
        )
        document = self.documents.observe_snapshot(
            source_code=grant.source_code,
            document_type="OTHER",
            snapshot=record_snapshot,
            title=grant.title + " — source record",
            extraction_status="EXTRACTED",
            parser_version="source-record-v1",
            commit=commit,
        )

        evidence = [
            {
                "field_path": "/title",
                "document_version_id": document.document_version_id,
                "verification_status": grant.verification_status,
                "evidence_text": grant.title,
                "extraction_method": "SOURCE_RECORD_SNAPSHOT",
                "extractor_version": "trusted-ingest-v1",
            },
            {
                "field_path": "/status",
                "document_version_id": document.document_version_id,
                "verification_status": grant.verification_status,
                "evidence_text": grant.status,
                "extraction_method": "SOURCE_RECORD_SNAPSHOT",
                "extractor_version": "trusted-ingest-v1",
            },
        ]
        if grant.summary:
            evidence.append(
                {
                    "field_path": "/summary",
                    "document_version_id": document.document_version_id,
                    "verification_status": grant.verification_status,
                    "evidence_text": grant.summary,
                    "extraction_method": "SOURCE_RECORD_SNAPSHOT",
                    "extractor_version": "trusted-ingest-v1",
                }
            )
        if grant.submission_close_at:
            evidence.append(
                {
                    "field_path": "/submission_close_at",
                    "document_version_id": document.document_version_id,
                    "verification_status": grant.verification_status,
                    "evidence_text": grant.submission_close_at,
                    "extraction_method": "SOURCE_RECORD_SNAPSHOT",
                    "extractor_version": "trusted-ingest-v1",
                }
            )

        payload = {
            "programme_id": grant.programme_id,
            "canonical_slug": grant.canonical_slug,
            "canonical_code": grant.source_external_id,
            "title": grant.title,
            "summary": grant.summary,
            "status": grant.status,
            "verification_status": grant.verification_status,
            "captured_at": grant.captured_at,
            "published_at": grant.published_at,
            "submission_open_at": grant.submission_open_at,
            "submission_close_at": grant.submission_close_at,
            "official_detail_url": grant.source_url,
            "currency_code": grant.currency_code,
            "normalization_version": "trusted-ingest-v1",
            "supported_activities": grant.supported_activities,
            "eligible_costs": grant.eligible_costs,
            "keywords": grant.keywords,
            "evidence": evidence,
        }
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        previous_payload = self.connection.execute(
            """SELECT c.payload_json
               FROM canonical_staging_items c
               JOIN source_registry s ON s.id=c.source_id
               WHERE s.code=? AND c.external_id=?
                 AND c.entity_type='GRANT_CALL' AND c.content_hash=?
               LIMIT 1""",
            (
                grant.source_code,
                grant.source_external_id,
                grant.content_hash,
            ),
        ).fetchone()
        force_reproject = (
            previous_payload is not None
            and str(previous_payload[0]) != payload_json
        )

        candidate = self.staging.stage(
            source_code=grant.source_code,
            external_id=grant.source_external_id,
            entity_type="GRANT_CALL",
            canonical_identity=grant.grant_call_id,
            payload=payload,
            content_hash=grant.content_hash,
            provenance_status=StagingProvenanceStatus.COMPLETE,
            source_run_id=source_run_id,
            now=current,
            commit=commit,
        )
        ready = self.staging.mark_validation(
            candidate.id,
            StagingValidationStatus.VALID,
            now=current,
            commit=commit,
        )
        publication = self.publisher.publish(
            ready.id,
            now=current,
            force_reproject=force_reproject,
            commit=commit,
        )
        return TrustedGrantIngestResult(
            source_record=source_record,
            document_version=document,
            publication=publication,
        )
