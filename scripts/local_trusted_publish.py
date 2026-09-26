from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dotacni_majak_ingestion.local_publish import SearchableGrant
from dotacni_majak_ingestion.outbox import OutboxStatus
from dotacni_majak_ingestion.search_projection import SqliteSearchProjection
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_ingestion.sqlite_outbox import SqliteOutboxRepository
from dotacni_majak_ingestion.trusted_ingest import TrustedGrantIngestor


_REQUIRED_TABLES = {
    "source_registry",
    "canonical_staging_items",
    "grant_search_documents",
    "outbox_events",
}


@dataclass(frozen=True, slots=True)
class TrustedLocalPublishSummary:
    database_path: str
    grants: int
    search_events_delivered: int


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
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        if _REQUIRED_TABLES.issubset(tables):
            matches.append(path.resolve())

    if not matches:
        raise RuntimeError(
            "No migrated Dotační maják D1 SQLite database found under "
            f"{root}"
        )
    if len(matches) > 1:
        listing = ", ".join(str(path) for path in sorted(matches))
        raise RuntimeError(
            "Multiple migrated D1 SQLite databases found; refusing to guess: "
            + listing
        )
    return matches[0]


def publish_grants_to_local_d1(
    grants: Iterable[SearchableGrant],
    *,
    raw_dir: str | Path,
    persist_root: str | Path,
    now: datetime | None = None,
) -> TrustedLocalPublishSummary:
    rows = list(grants)
    if not rows:
        raise ValueError("refusing to publish an empty source run")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)

    database_path = discover_local_d1_database(persist_root)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    store = LocalRawSnapshotStore(raw_dir)
    ingestor = TrustedGrantIngestor(connection)
    projection = SqliteSearchProjection(connection)
    outbox = SqliteOutboxRepository(connection)
    delivered = 0

    try:
        for grant in rows:
            snapshot = store.load_by_sha256(
                source_code=grant.source_code,
                sha256=grant.content_hash,
            )
            result = ingestor.ingest(
                grant,
                record_snapshot=snapshot,
                now=current,
            )
            dedupe_key = (
                "SEARCH_REINDEX_REQUIRED:"
                + result.publication.grant_call_version_id
            )
            event = outbox.claim_by_dedupe_key(
                dedupe_key,
                worker_id="local-refresh-search",
                now=current,
                lease_seconds=120,
            )
            if event is not None:
                try:
                    projection.handle_outbox(event)
                    outbox.mark_delivered(
                        event.id,
                        worker_id="local-refresh-search",
                        now=current,
                    )
                    delivered += 1
                except Exception as exc:
                    outbox.mark_failed(
                        event.id,
                        worker_id="local-refresh-search",
                        error=exc,
                        now=current,
                        max_attempts=5,
                        retry_after_seconds=0,
                    )
                    raise
            else:
                existing = outbox.get_by_dedupe_key(dedupe_key)
                if existing is None or existing.status is not OutboxStatus.DELIVERED:
                    raise RuntimeError(
                        "search projection event exists but is not claimable/delivered: "
                        + dedupe_key
                    )
    finally:
        connection.close()

    return TrustedLocalPublishSummary(
        database_path=str(database_path),
        grants=len(rows),
        search_events_delivered=delivered,
    )
