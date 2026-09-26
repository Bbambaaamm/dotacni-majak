from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return current.astimezone(timezone.utc)


class StagingValidationStatus(str, Enum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class StagingProvenanceStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class StagingState(str, Enum):
    STAGED = "STAGED"
    READY = "READY"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


@dataclass(frozen=True, slots=True)
class StagedCanonicalCandidate:
    id: str
    source_code: str
    external_id: str
    entity_type: str
    canonical_identity: str
    payload_json: str
    content_hash: str
    validation_status: StagingValidationStatus
    provenance_status: StagingProvenanceStatus
    state: StagingState
    attempts: int
    created_at: str
    updated_at: str
    source_run_id: str | None = None
    ingestion_run_id: str | None = None
    last_error: str | None = None
    published_entity_id: str | None = None
    published_at: str | None = None

    @property
    def payload(self) -> object:
        return json.loads(self.payload_json)


class SqliteCanonicalStagingRepository:
    """D1-compatible staging store before immutable canonical publication.

    Distinct upstream content hashes create distinct candidates. Retrying the
    same source/external/entity/hash is idempotent and never duplicates rows.
    """

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
    def _candidate_id(
        source_id: str,
        external_id: str,
        entity_type: str,
        content_hash: str,
    ) -> str:
        digest = hashlib.sha256(
            "\x1f".join(
                (source_id, external_id, entity_type, content_hash)
            ).encode("utf-8")
        ).hexdigest()
        return f"stg_{digest[:40]}"

    @staticmethod
    def _payload_json(payload: Mapping[str, object]) -> str:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def _row_to_candidate(
        self,
        row: tuple[object, ...],
    ) -> StagedCanonicalCandidate:
        return StagedCanonicalCandidate(
            id=str(row[0]),
            source_code=str(row[1]),
            external_id=str(row[2]),
            entity_type=str(row[3]),
            canonical_identity=str(row[4]),
            payload_json=str(row[5]),
            content_hash=str(row[6]),
            validation_status=StagingValidationStatus(str(row[7])),
            provenance_status=StagingProvenanceStatus(str(row[8])),
            state=StagingState(str(row[9])),
            attempts=int(row[10]),
            last_error=str(row[11]) if row[11] is not None else None,
            source_run_id=str(row[12]) if row[12] is not None else None,
            ingestion_run_id=str(row[13]) if row[13] is not None else None,
            published_entity_id=(
                str(row[14]) if row[14] is not None else None
            ),
            published_at=str(row[15]) if row[15] is not None else None,
            created_at=str(row[16]),
            updated_at=str(row[17]),
        )

    def _select_one(
        self,
        where: str,
        params: tuple[object, ...],
    ) -> StagedCanonicalCandidate | None:
        row = self.connection.execute(
            f"""SELECT
                   c.id, s.code, c.external_id, c.entity_type,
                   c.canonical_identity, c.payload_json, c.content_hash,
                   c.validation_status, c.provenance_status, c.state,
                   c.attempts, c.last_error, c.source_run_id,
                   c.ingestion_run_id, c.published_entity_id,
                   c.published_at, c.created_at, c.updated_at
                FROM canonical_staging_items c
                JOIN source_registry s ON s.id = c.source_id
                WHERE {where}
                LIMIT 1""",
            params,
        ).fetchone()
        return self._row_to_candidate(row) if row else None

    def get(self, candidate_id: str) -> StagedCanonicalCandidate | None:
        return self._select_one("c.id = ?", (candidate_id,))

    def stage(
        self,
        *,
        source_code: str,
        external_id: str,
        entity_type: str,
        canonical_identity: str,
        payload: Mapping[str, object],
        content_hash: str,
        provenance_status: StagingProvenanceStatus,
        source_run_id: str | None = None,
        ingestion_run_id: str | None = None,
        retry: bool = False,
        now: datetime | None = None,
    ) -> StagedCanonicalCandidate:
        if not external_id.strip():
            raise ValueError("external_id must not be empty")
        if not canonical_identity.strip():
            raise ValueError("canonical_identity must not be empty")
        if entity_type not in {
            "GRANT_CALL", "PROGRAMME", "PROVIDER", "DOCUMENT", "OTHER"
        }:
            raise ValueError("unsupported entity_type")
        if not _HASH_RE.fullmatch(content_hash):
            raise ValueError("content_hash must be lowercase SHA-256 hex")

        source_id = self._source_id(source_code)
        candidate_id = self._candidate_id(
            source_id,
            external_id,
            entity_type,
            content_hash,
        )
        payload_json = self._payload_json(payload)
        timestamp = _utc(now).isoformat()

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._select_one("c.id = ?", (candidate_id,))
            if existing is None:
                self.connection.execute(
                    """INSERT INTO canonical_staging_items(
                         id, source_id, source_run_id, ingestion_run_id,
                         external_id, entity_type, canonical_identity,
                         payload_json, content_hash, validation_status,
                         provenance_status, state, attempts, last_error,
                         created_at, updated_at
                       ) VALUES (
                         ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING',
                         ?, 'STAGED', 0, NULL, ?, ?
                       )""",
                    (
                        candidate_id,
                        source_id,
                        source_run_id,
                        ingestion_run_id,
                        external_id,
                        entity_type,
                        canonical_identity,
                        payload_json,
                        content_hash,
                        provenance_status.value,
                        timestamp,
                        timestamp,
                    ),
                )
            elif existing.state is not StagingState.PUBLISHED:
                if retry:
                    self.connection.execute(
                        """UPDATE canonical_staging_items
                           SET source_run_id = ?,
                               ingestion_run_id = ?,
                               canonical_identity = ?,
                               payload_json = ?,
                               provenance_status = ?,
                               validation_status = 'PENDING',
                               state = 'STAGED',
                               attempts = attempts + 1,
                               last_error = NULL,
                               updated_at = ?
                           WHERE id = ?""",
                        (
                            source_run_id,
                            ingestion_run_id,
                            canonical_identity,
                            payload_json,
                            provenance_status.value,
                            timestamp,
                            candidate_id,
                        ),
                    )
                else:
                    self.connection.execute(
                        """UPDATE canonical_staging_items
                           SET source_run_id = COALESCE(?, source_run_id),
                               ingestion_run_id = COALESCE(?, ingestion_run_id),
                               canonical_identity = ?,
                               payload_json = ?,
                               provenance_status = ?,
                               updated_at = ?
                           WHERE id = ?""",
                        (
                            source_run_id,
                            ingestion_run_id,
                            canonical_identity,
                            payload_json,
                            provenance_status.value,
                            timestamp,
                            candidate_id,
                        ),
                    )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        candidate = self.get(candidate_id)
        if candidate is None:
            raise RuntimeError("staging candidate was not persisted")
        return candidate

    def mark_validation(
        self,
        candidate_id: str,
        status: StagingValidationStatus,
        *,
        error: str | None = None,
        now: datetime | None = None,
    ) -> StagedCanonicalCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate.state is StagingState.PUBLISHED:
            return candidate

        if status is StagingValidationStatus.VALID:
            if candidate.provenance_status is StagingProvenanceStatus.MISSING:
                raise ValueError(
                    "candidate with missing provenance cannot become READY"
                )
            state = StagingState.READY
            error = None
        elif status is StagingValidationStatus.INVALID:
            state = StagingState.REJECTED
        else:
            state = StagingState.STAGED

        result = self.connection.execute(
            """UPDATE canonical_staging_items
               SET validation_status = ?, state = ?, last_error = ?,
                   updated_at = ?
               WHERE id = ? AND state <> 'PUBLISHED'""",
            (
                status.value,
                state.value,
                error,
                _utc(now).isoformat(),
                candidate_id,
            ),
        )
        if result.rowcount != 1:
            raise RuntimeError("staging validation transition failed")
        self.connection.commit()
        updated = self.get(candidate_id)
        if updated is None:
            raise RuntimeError("staging candidate disappeared")
        return updated

    def mark_published(
        self,
        candidate_id: str,
        *,
        published_entity_id: str,
        now: datetime | None = None,
    ) -> StagedCanonicalCandidate:
        if not published_entity_id.strip():
            raise ValueError("published_entity_id must not be empty")
        timestamp = _utc(now).isoformat()
        result = self.connection.execute(
            """UPDATE canonical_staging_items
               SET state = 'PUBLISHED',
                   published_entity_id = ?,
                   published_at = ?,
                   updated_at = ?
               WHERE id = ? AND state = 'READY'""",
            (
                published_entity_id,
                timestamp,
                timestamp,
                candidate_id,
            ),
        )
        if result.rowcount != 1:
            candidate = self.get(candidate_id)
            if (
                candidate is not None
                and candidate.state is StagingState.PUBLISHED
                and candidate.published_entity_id == published_entity_id
            ):
                return candidate
            raise RuntimeError("only READY candidates may be published")
        self.connection.commit()
        updated = self.get(candidate_id)
        if updated is None:
            raise RuntimeError("staging candidate disappeared")
        return updated

    def list_by_state(
        self,
        state: StagingState,
        *,
        limit: int = 100,
    ) -> list[StagedCanonicalCandidate]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = self.connection.execute(
            """SELECT
                 c.id, s.code, c.external_id, c.entity_type,
                 c.canonical_identity, c.payload_json, c.content_hash,
                 c.validation_status, c.provenance_status, c.state,
                 c.attempts, c.last_error, c.source_run_id,
                 c.ingestion_run_id, c.published_entity_id,
                 c.published_at, c.created_at, c.updated_at
               FROM canonical_staging_items c
               JOIN source_registry s ON s.id = c.source_id
               WHERE c.state = ?
               ORDER BY c.updated_at ASC, c.id ASC
               LIMIT ?""",
            (state.value, limit),
        ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def cleanup_terminal_before(self, cutoff: datetime) -> int:
        cutoff_iso = _utc(cutoff).isoformat()
        result = self.connection.execute(
            """DELETE FROM canonical_staging_items
               WHERE state IN ('PUBLISHED','REJECTED')
                 AND updated_at < ?""",
            (cutoff_iso,),
        )
        self.connection.commit()
        return int(result.rowcount)
