from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from dotacni_majak_ingestion.local_publish import SearchableGrant
from dotacni_majak_ingestion.outbox import OutboxStatus
from dotacni_majak_ingestion.search_projection import SqliteSearchProjection
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_ingestion.source_records import SourceRecordChange
from dotacni_majak_ingestion.sqlite_outbox import SqliteOutboxRepository
from dotacni_majak_ingestion.trusted_ingest import TrustedGrantIngestor


_REQUIRED_TABLES = {
    "source_registry",
    "source_runs",
    "canonical_staging_items",
    "grant_search_documents",
    "outbox_events",
}
_REQUIRED_INDEXES = {
    "idx_source_documents_identity",
    "idx_grant_versions_call_content",
}


@dataclass(frozen=True, slots=True)
class TrustedLocalPublishSummary:
    database_path: str
    grants: int
    search_events_delivered: int
    source_run_id: str


def _has_current_identity_schema(connection: sqlite3.Connection) -> bool:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if not _REQUIRED_TABLES.issubset(tables):
        return False
    indexes = {
        str(row[0]): str(row[1] or "")
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index'"
        )
    }
    if not _REQUIRED_INDEXES.issubset(indexes):
        return False
    source_document_index = " ".join(
        indexes["idx_source_documents_identity"].lower().split()
    )
    grant_version_index = " ".join(
        indexes["idx_grant_versions_call_content"].lower().split()
    )
    return (
        "create unique index" in source_document_index
        and "source_id, document_type, source_url" in source_document_index
        and "create unique index" in grant_version_index
        and "grant_call_id, content_hash" in grant_version_index
    )


def discover_local_d1_database(persist_root: str | Path) -> Path:
    root = Path(persist_root).resolve()
    if not root.exists():
        raise FileNotFoundError(
            f"Wrangler local persistence does not exist: {root}. "
            "Run D1 migrations first."
        )
    matches: list[Path] = []
    for path in root.rglob("*.sqlite"):
        try:
            connection = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro",
                uri=True,
                timeout=2,
            )
            try:
                current = _has_current_identity_schema(connection)
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        if current:
            matches.append(path.resolve())

    if not matches:
        raise RuntimeError(
            "No fully migrated Dotační maják D1 SQLite database found under "
            f"{root}; migrations through identity indexes 0025/0026 are required."
        )
    if len(matches) > 1:
        listing = ", ".join(str(path) for path in sorted(matches))
        raise RuntimeError(
            "Multiple migrated D1 SQLite databases found; refusing to guess: "
            + listing
        )
    return matches[0]


def _assert_single_source(rows: list[SearchableGrant]) -> SearchableGrant:
    first = rows[0]
    source_identity = (
        first.source_id,
        first.source_code,
        first.source_name,
        first.source_base_url,
        first.adapter_key,
        first.retrieval_mode,
    )
    for grant in rows:
        grant.validate()
        candidate = (
            grant.source_id,
            grant.source_code,
            grant.source_name,
            grant.source_base_url,
            grant.adapter_key,
            grant.retrieval_mode,
        )
        if candidate != source_identity:
            raise ValueError(
                "trusted local publish accepts exactly one source per atomic batch"
            )
    return first


def _upsert_source_registry(
    connection: sqlite3.Connection,
    grant: SearchableGrant,
) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
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
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _start_source_run(
    connection: sqlite3.Connection,
    grant: SearchableGrant,
    *,
    adapter_version: str,
    started_at: str,
) -> str:
    if not adapter_version.strip():
        raise ValueError("adapter_version must not be empty")
    run_id = f"source-run:{grant.source_code.lower()}:{uuid4().hex}"
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """INSERT INTO source_runs(
                 id,source_id,started_at,finished_at,status,records_seen,
                 new_records,changed_records,error_count,adapter_version
               ) VALUES (?, ?, ?, NULL, 'RUNNING', 0, 0, 0, 0, ?)""",
            (run_id, grant.source_id, started_at, adapter_version),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return run_id


def _mark_failed_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    finished_at: str,
    records_seen: int,
    new_records: int,
    changed_records: int,
) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """UPDATE source_runs
               SET finished_at=?, status='FAILED', records_seen=?,
                   new_records=?, changed_records=?, error_count=1
               WHERE id=?""",
            (
                finished_at,
                records_seen,
                new_records,
                changed_records,
                run_id,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def publish_grants_to_local_d1(
    grants: Iterable[SearchableGrant],
    *,
    raw_dir: str | Path,
    persist_root: str | Path,
    adapter_version: str,
    now: datetime | None = None,
) -> TrustedLocalPublishSummary:
    rows = list(grants)
    if not rows:
        raise ValueError("refusing to publish an empty source run")
    source = _assert_single_source(rows)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)
    timestamp = current.isoformat()

    database_path = discover_local_d1_database(persist_root)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    store = LocalRawSnapshotStore(raw_dir)
    ingestor = TrustedGrantIngestor(connection)
    projection = SqliteSearchProjection(connection)
    outbox = SqliteOutboxRepository(connection)

    _upsert_source_registry(connection, source)
    source_run_id = _start_source_run(
        connection,
        source,
        adapter_version=adapter_version,
        started_at=timestamp,
    )

    delivered = 0
    records_seen = 0
    new_records = 0
    changed_records = 0

    try:
        connection.execute("BEGIN IMMEDIATE")
        for grant in rows:
            if grant.raw_snapshot_id is not None:
                snapshot = store.load_by_snapshot_id(grant.raw_snapshot_id)
            else:
                try:
                    snapshot = store.load_by_sha256(
                        source_code=grant.source_code,
                        sha256=grant.content_hash,
                        source_url=grant.source_url,
                    )
                except FileNotFoundError:
                    # Backward compatibility for pre-URL-qualified snapshots:
                    # hash-only fallback is accepted only when provenance is
                    # unambiguous; the store fails closed otherwise.
                    snapshot = store.load_by_sha256(
                        source_code=grant.source_code,
                        sha256=grant.content_hash,
                    )
            result = ingestor.ingest(
                grant,
                record_snapshot=snapshot,
                source_run_id=source_run_id,
                now=current,
                commit=False,
            )
            records_seen += 1
            if result.source_record.change is SourceRecordChange.NEW:
                new_records += 1
            elif result.source_record.change is SourceRecordChange.CHANGED:
                changed_records += 1

            search_keys = [
                key
                for key in result.publication.outbox_dedupe_keys
                if key.startswith("SEARCH_REINDEX_REQUIRED:")
            ]
            if len(search_keys) > 1:
                raise RuntimeError(
                    "publication emitted more than one search event"
                )
            if search_keys:
                dedupe_key = search_keys[0]
                event = outbox.claim_by_dedupe_key(
                    dedupe_key,
                    worker_id="local-refresh-search",
                    now=current,
                    lease_seconds=120,
                    commit=False,
                )
                if event is None:
                    existing = outbox.get_by_dedupe_key(dedupe_key)
                    if (
                        existing is None
                        or existing.status is not OutboxStatus.DELIVERED
                    ):
                        raise RuntimeError(
                            "search projection event exists but is not "
                            "claimable/delivered: " + dedupe_key
                        )
                else:
                    projection.handle_outbox(event, commit=False)
                    outbox.mark_delivered(
                        event.id,
                        worker_id="local-refresh-search",
                        now=current,
                        commit=False,
                    )
                    delivered += 1

        connection.execute(
            """UPDATE source_runs
               SET finished_at=?, status='COMPLETED', records_seen=?,
                   new_records=?, changed_records=?, error_count=0
               WHERE id=?""",
            (
                timestamp,
                records_seen,
                new_records,
                changed_records,
                source_run_id,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        _mark_failed_run(
            connection,
            run_id=source_run_id,
            finished_at=timestamp,
            records_seen=records_seen,
            new_records=new_records,
            changed_records=changed_records,
        )
        raise
    finally:
        connection.close()

    return TrustedLocalPublishSummary(
        database_path=str(database_path),
        grants=len(rows),
        search_events_delivered=delivered,
        source_run_id=source_run_id,
    )
