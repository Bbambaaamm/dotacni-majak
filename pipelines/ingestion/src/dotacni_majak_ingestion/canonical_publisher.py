from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .field_evidence import (
    FieldEvidenceIntegrityError,
    FieldEvidenceRecord,
    FieldEvidenceRepository,
)
from .outbox import OutboxEventType
from .sqlite_outbox import SqliteOutboxRepository
from .staging import (
    SqliteCanonicalStagingRepository,
    StagingProvenanceStatus,
    StagingState,
    StagingValidationStatus,
)


_ALLOWED_STATUSES = {
    "DRAFT", "ANNOUNCED", "PLANNED", "OPEN", "PAUSED",
    "CLOSED", "CANCELLED", "ARCHIVED",
}
_ALLOWED_VERIFICATION = {
    "AUTO_EXTRACTED", "PARTIALLY_VERIFIED", "VERIFIED", "NEEDS_REVIEW",
}


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


class PublicationErrorCode(str, Enum):
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
    CANDIDATE_NOT_READY = "CANDIDATE_NOT_READY"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    PROGRAMME_MISSING = "PROGRAMME_MISSING"
    SOURCE_RECORD_MISSING = "SOURCE_RECORD_MISSING"
    SOURCE_RECORD_MISMATCH = "SOURCE_RECORD_MISMATCH"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    PUBLISHED_ENTITY_MISSING = "PUBLISHED_ENTITY_MISSING"


class CanonicalPublicationError(RuntimeError):
    def __init__(self, code: PublicationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class GrantPublicationResult:
    grant_call_id: str
    grant_call_version_id: str
    version_number: int
    created_version: bool
    evidence_count: int
    outbox_event_count: int
    outbox_dedupe_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _GrantPayload:
    programme_id: str
    canonical_slug: str
    title: str
    summary: str | None
    status: str
    verification_status: str
    captured_at: str
    canonical_code: str | None
    published_at: str | None
    submission_open_at: str | None
    submission_close_at: str | None
    application_url: str | None
    official_detail_url: str | None
    currency_code: str | None
    normalization_version: str | None
    evidence: tuple[dict[str, Any], ...]


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            f"{key} must be a non-empty string",
        )
    return value.strip()


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            f"{key} must be a string or null",
        )
    return value


def _parse_payload(raw: object, *, default_captured_at: str) -> _GrantPayload:
    if not isinstance(raw, dict):
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            "staged grant payload must be a JSON object",
        )
    status = _required_text(raw, "status")
    if status not in _ALLOWED_STATUSES:
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            f"unsupported grant status {status!r}",
        )
    verification = _required_text(raw, "verification_status")
    if verification not in _ALLOWED_VERIFICATION:
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            f"unsupported verification_status {verification!r}",
        )
    evidence_raw = raw.get("evidence", [])
    if not isinstance(evidence_raw, list) or not all(
        isinstance(item, dict) for item in evidence_raw
    ):
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            "evidence must be an array of objects",
        )
    captured_at = raw.get("captured_at", default_captured_at)
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise CanonicalPublicationError(
            PublicationErrorCode.PAYLOAD_INVALID,
            "captured_at must be a non-empty string",
        )
    return _GrantPayload(
        programme_id=_required_text(raw, "programme_id"),
        canonical_slug=_required_text(raw, "canonical_slug"),
        title=_required_text(raw, "title"),
        summary=_optional_text(raw, "summary"),
        status=status,
        verification_status=verification,
        captured_at=captured_at,
        canonical_code=_optional_text(raw, "canonical_code"),
        published_at=_optional_text(raw, "published_at"),
        submission_open_at=_optional_text(raw, "submission_open_at"),
        submission_close_at=_optional_text(raw, "submission_close_at"),
        application_url=_optional_text(raw, "application_url"),
        official_detail_url=_optional_text(raw, "official_detail_url"),
        currency_code=_optional_text(raw, "currency_code"),
        normalization_version=_optional_text(raw, "normalization_version"),
        evidence=tuple(evidence_raw),
    )


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join("" if part is None else str(part) for part in parts)
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _can_migrate_legacy_programme_identity(
    source_code: str,
    old_programme_id: str,
    new_programme_id: str,
) -> bool:
    namespace = {"DOTACEEU": "dotaceeu", "EU_FT": "eu-ft"}.get(source_code)
    if namespace is None:
        return False
    legacy = re.fullmatch(
        rf"programme:{re.escape(namespace)}:[0-9a-f]{{16}}",
        old_programme_id,
    )
    return bool(legacy) and new_programme_id.startswith(
        f"programme:{namespace}:"
    )


class SqliteCanonicalPublisher:
    """Publish one READY staged GrantCall candidate as one atomic transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.staging = SqliteCanonicalStagingRepository(connection)
        self.evidence = FieldEvidenceRepository(connection)
        self.outbox = SqliteOutboxRepository(connection)

    def _already_published(
        self,
        candidate_id: str,
        published_entity_id: str | None,
    ) -> GrantPublicationResult:
        if published_entity_id is None:
            raise CanonicalPublicationError(
                PublicationErrorCode.PUBLISHED_ENTITY_MISSING,
                "published candidate has no published_entity_id",
            )
        row = self.connection.execute(
            """SELECT grant_call_id, version_number
               FROM grant_call_versions WHERE id=?""",
            (published_entity_id,),
        ).fetchone()
        if row is None:
            raise CanonicalPublicationError(
                PublicationErrorCode.PUBLISHED_ENTITY_MISSING,
                f"published version {published_entity_id!r} does not exist",
            )
        evidence_count = self.connection.execute(
            "SELECT COUNT(*) FROM field_evidence WHERE entity_id=?",
            (published_entity_id,),
        ).fetchone()[0]
        outbox_count = self.connection.execute(
            "SELECT COUNT(*) FROM outbox_events WHERE aggregate_id=?",
            (str(row[0]),),
        ).fetchone()[0]
        return GrantPublicationResult(
            grant_call_id=str(row[0]),
            grant_call_version_id=published_entity_id,
            version_number=int(row[1]),
            created_version=False,
            evidence_count=int(evidence_count),
            outbox_event_count=int(outbox_count),
        )

    def publish(
        self,
        candidate_id: str,
        *,
        now: datetime | None = None,
        force_reproject: bool = False,
        commit: bool = True,
    ) -> GrantPublicationResult:
        timestamp = _utc(now).isoformat()
        candidate = self.staging.get(candidate_id)
        if candidate is None:
            raise CanonicalPublicationError(
                PublicationErrorCode.CANDIDATE_NOT_FOUND,
                f"staging candidate {candidate_id!r} not found",
            )

        was_published = candidate.state is StagingState.PUBLISHED
        if not was_published and (
            candidate.state is not StagingState.READY
            or candidate.validation_status is not StagingValidationStatus.VALID
            or candidate.provenance_status is StagingProvenanceStatus.MISSING
        ):
            raise CanonicalPublicationError(
                PublicationErrorCode.CANDIDATE_NOT_READY,
                "only VALID READY candidates with provenance may be published",
            )
        if candidate.entity_type != "GRANT_CALL":
            raise CanonicalPublicationError(
                PublicationErrorCode.PAYLOAD_INVALID,
                "canonical publisher currently accepts GRANT_CALL candidates",
            )

        payload = _parse_payload(
            candidate.payload,
            default_captured_at=candidate.updated_at,
        )
        grant_call_id = candidate.canonical_identity
        version_id = _stable_id(
            "gcv_", grant_call_id, candidate.content_hash
        )

        source = self.connection.execute(
            "SELECT id FROM source_registry WHERE code=?",
            (candidate.source_code,),
        ).fetchone()
        if source is None:
            raise CanonicalPublicationError(
                PublicationErrorCode.SOURCE_RECORD_MISSING,
                f"source {candidate.source_code!r} is not registered",
            )
        source_id = str(source[0])

        source_record = self.connection.execute(
            """SELECT id, content_hash, first_seen_at
               FROM source_records
               WHERE source_id=? AND external_id=?""",
            (source_id, candidate.external_id),
        ).fetchone()
        if source_record is None:
            raise CanonicalPublicationError(
                PublicationErrorCode.SOURCE_RECORD_MISSING,
                "source record must be observed before canonical publication",
            )
        if str(source_record[1] or "") != candidate.content_hash:
            raise CanonicalPublicationError(
                PublicationErrorCode.SOURCE_RECORD_MISMATCH,
                "staging candidate hash differs from latest source record hash",
            )

        if self.connection.execute(
            "SELECT 1 FROM programmes WHERE id=?",
            (payload.programme_id,),
        ).fetchone() is None:
            raise CanonicalPublicationError(
                PublicationErrorCode.PROGRAMME_MISSING,
                f"programme {payload.programme_id!r} does not exist",
            )

        if commit:
            self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing_call = self.connection.execute(
                """SELECT programme_id, canonical_slug, current_version_id
                   FROM grant_calls WHERE id=?""",
                (grant_call_id,),
            ).fetchone()
            current_before = (
                str(existing_call[2])
                if existing_call is not None and existing_call[2] is not None
                else None
            )
            slug_owner = self.connection.execute(
                "SELECT id FROM grant_calls WHERE canonical_slug=?",
                (payload.canonical_slug,),
            ).fetchone()
            if slug_owner is not None and str(slug_owner[0]) != grant_call_id:
                raise CanonicalPublicationError(
                    PublicationErrorCode.IDENTITY_CONFLICT,
                    "canonical_slug belongs to another GrantCall",
                )

            programme_migrated = False
            if existing_call is None:
                self.connection.execute(
                    """INSERT INTO grant_calls(
                         id, programme_id, canonical_code, canonical_slug,
                         current_version_id, current_status, current_title,
                         first_seen_at, first_published_at, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
                    (
                        grant_call_id,
                        payload.programme_id,
                        payload.canonical_code,
                        payload.canonical_slug,
                        payload.status,
                        payload.title,
                        str(source_record[2]),
                        payload.published_at,
                        timestamp,
                        timestamp,
                    ),
                )
            else:
                old_programme_id = str(existing_call[0])
                old_slug = str(existing_call[1])
                if old_slug != payload.canonical_slug:
                    raise CanonicalPublicationError(
                        PublicationErrorCode.IDENTITY_CONFLICT,
                        "stable GrantCall identity conflicts with existing slug",
                    )
                if old_programme_id != payload.programme_id:
                    if not _can_migrate_legacy_programme_identity(
                        candidate.source_code,
                        old_programme_id,
                        payload.programme_id,
                    ):
                        raise CanonicalPublicationError(
                            PublicationErrorCode.IDENTITY_CONFLICT,
                            "stable GrantCall identity conflicts with existing programme",
                        )
                    self.connection.execute(
                        """UPDATE grant_calls
                           SET programme_id=?, updated_at=?
                           WHERE id=?""",
                        (payload.programme_id, timestamp, grant_call_id),
                    )
                    programme_migrated = True

            existing_version = self.connection.execute(
                """SELECT
                     id, version_number, title, summary, status, published_at,
                     submission_open_at, submission_close_at, application_url,
                     official_detail_url, currency_code, normalization_version,
                     verification_status
                   FROM grant_call_versions
                   WHERE grant_call_id=? AND content_hash=?""",
                (grant_call_id, candidate.content_hash),
            ).fetchone()

            created_version = existing_version is None
            normalized_changed = False
            if created_version:
                version_number = int(
                    self.connection.execute(
                        """SELECT COALESCE(MAX(version_number),0)+1
                           FROM grant_call_versions
                           WHERE grant_call_id=?""",
                        (grant_call_id,),
                    ).fetchone()[0]
                )
                self.connection.execute(
                    """INSERT INTO grant_call_versions(
                         id, grant_call_id, version_number, captured_at,
                         effective_from, effective_to, title, summary, status,
                         published_at, submission_open_at, submission_close_at,
                         application_url, official_detail_url, currency_code,
                         normalization_version, content_hash,
                         verification_status, created_at
                       ) VALUES (
                         ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?
                       )""",
                    (
                        version_id,
                        grant_call_id,
                        version_number,
                        payload.captured_at,
                        payload.title,
                        payload.summary,
                        payload.status,
                        payload.published_at,
                        payload.submission_open_at,
                        payload.submission_close_at,
                        payload.application_url,
                        payload.official_detail_url,
                        payload.currency_code,
                        payload.normalization_version,
                        candidate.content_hash,
                        payload.verification_status,
                        timestamp,
                    ),
                )
            else:
                version_id = str(existing_version[0])
                version_number = int(existing_version[1])
                stored_normalized = tuple(existing_version[2:])
                incoming_normalized = (
                    payload.title,
                    payload.summary,
                    payload.status,
                    payload.published_at,
                    payload.submission_open_at,
                    payload.submission_close_at,
                    payload.application_url,
                    payload.official_detail_url,
                    payload.currency_code,
                    payload.normalization_version,
                    payload.verification_status,
                )
                normalized_changed = (
                    stored_normalized != incoming_normalized
                    or force_reproject
                )
                if normalized_changed:
                    self.connection.execute(
                        """UPDATE grant_call_versions
                           SET title=?, summary=?, status=?, published_at=?,
                               submission_open_at=?, submission_close_at=?,
                               application_url=?, official_detail_url=?,
                               currency_code=?, normalization_version=?,
                               verification_status=?
                           WHERE id=?""",
                        (
                            payload.title,
                            payload.summary,
                            payload.status,
                            payload.published_at,
                            payload.submission_open_at,
                            payload.submission_close_at,
                            payload.application_url,
                            payload.official_detail_url,
                            payload.currency_code,
                            payload.normalization_version,
                            payload.verification_status,
                            version_id,
                        ),
                    )

            reactivation_needed = current_before != version_id
            publication_changed = (
                created_version
                or reactivation_needed
                or normalized_changed
                or programme_migrated
            )

            evidence_count = 0
            if publication_changed:
                for item in payload.evidence:
                    field_path = _required_text(item, "field_path")
                    document_version_id = _required_text(
                        item, "document_version_id"
                    )
                    verification_status = _required_text(
                        item, "verification_status"
                    )
                    evidence_id = _stable_id(
                        "fe_",
                        version_id,
                        field_path,
                        document_version_id,
                        item.get("document_section_id"),
                        item.get("page_from"),
                        item.get("page_to"),
                        item.get("evidence_text"),
                    )
                    record = FieldEvidenceRecord(
                        id=evidence_id,
                        entity_type="GRANT_CALL_VERSION",
                        entity_id=version_id,
                        field_path=field_path,
                        document_version_id=document_version_id,
                        verification_status=verification_status,
                        created_at=timestamp,
                        document_section_id=item.get("document_section_id"),
                        page_from=item.get("page_from"),
                        page_to=item.get("page_to"),
                        evidence_text=item.get("evidence_text"),
                        extraction_method=item.get("extraction_method"),
                        extractor_version=item.get("extractor_version"),
                        confidence_ppm=item.get("confidence_ppm"),
                    )
                    try:
                        self.evidence.save(record, commit=False)
                    except (
                        FieldEvidenceIntegrityError,
                        sqlite3.IntegrityError,
                    ) as exc:
                        raise CanonicalPublicationError(
                            PublicationErrorCode.EVIDENCE_INVALID,
                            str(exc),
                        ) from exc
                    evidence_count += 1

                self.connection.execute(
                    """UPDATE grant_calls
                       SET programme_id=?, canonical_code=?,
                           current_version_id=?, current_status=?,
                           current_title=?, updated_at=?
                       WHERE id=?""",
                    (
                        payload.programme_id,
                        payload.canonical_code,
                        version_id,
                        payload.status,
                        payload.title,
                        timestamp,
                        grant_call_id,
                    ),
                )

            self.connection.execute(
                """UPDATE source_records
                   SET grant_call_id=?, content_hash=?,
                       presence_state='SEEN', missing_run_count=0
                   WHERE source_id=? AND external_id=?""",
                (
                    grant_call_id,
                    candidate.content_hash,
                    source_id,
                    candidate.external_id,
                ),
            )

            outbox_keys: list[str] = []
            if publication_changed:
                event_payload = {
                    "grantCallId": grant_call_id,
                    "grantCallVersionId": version_id,
                    "sourceCode": candidate.source_code,
                }
                if created_version:
                    suffix = ""
                else:
                    activation_seed = "\x1f".join(
                        (
                            candidate.source_run_id or candidate.updated_at,
                            current_before or "",
                            version_id,
                            json.dumps(
                                candidate.payload,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        )
                    )
                    activation = hashlib.sha256(
                        activation_seed.encode("utf-8")
                    ).hexdigest()[:20]
                    suffix = f":activation:{activation}"

                for event_type in (
                    OutboxEventType.SEARCH_REINDEX_REQUIRED,
                    OutboxEventType.CHANGE_DETECTION_REQUIRED,
                ):
                    dedupe_key = (
                        f"{event_type.value}:{version_id}{suffix}"
                    )
                    self.outbox.enqueue(
                        event_type=event_type,
                        aggregate_type="GRANT_CALL",
                        aggregate_id=grant_call_id,
                        payload=event_payload,
                        dedupe_key=dedupe_key,
                        now=_utc(now),
                        commit=False,
                    )
                    outbox_keys.append(dedupe_key)

            if was_published:
                self.connection.execute(
                    """UPDATE canonical_staging_items
                       SET published_entity_id=?, updated_at=?
                       WHERE id=? AND state='PUBLISHED'""",
                    (version_id, timestamp, candidate.id),
                )
            else:
                staged = self.connection.execute(
                    """UPDATE canonical_staging_items
                       SET state='PUBLISHED', published_entity_id=?,
                           published_at=?, updated_at=?
                       WHERE id=? AND state='READY'""",
                    (version_id, timestamp, timestamp, candidate.id),
                )
                if staged.rowcount != 1:
                    raise CanonicalPublicationError(
                        PublicationErrorCode.CANDIDATE_NOT_READY,
                        "staging candidate changed during publication",
                    )

            if commit:
                self.connection.commit()
        except Exception:
            if commit:
                self.connection.rollback()
            raise

        return GrantPublicationResult(
            grant_call_id=grant_call_id,
            grant_call_version_id=version_id,
            version_number=version_number,
            created_version=created_version,
            evidence_count=evidence_count,
            outbox_event_count=len(outbox_keys),
            outbox_dedupe_keys=tuple(outbox_keys),
        )
