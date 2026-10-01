from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .outbox import OutboxEvent, OutboxEventType


@dataclass(frozen=True, slots=True)
class SearchProjectionResult:
    grant_call_id: str
    grant_call_version_id: str
    indexed: bool


class SqliteSearchProjection:
    """Idempotent canonical GrantCall -> lexical search projection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")

    def reindex_grant_call(
        self,
        grant_call_id: str,
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> SearchProjectionResult:
        row = self.connection.execute(
            """SELECT
                 g.current_version_id, v.title, COALESCE(v.summary,''),
                 v.status, v.submission_close_at, g.canonical_code,
                 pr.name, p.name
               FROM grant_calls g
               JOIN grant_call_versions v ON v.id=g.current_version_id
               JOIN programmes pr ON pr.id=g.programme_id
               JOIN providers p ON p.id=pr.provider_id
               WHERE g.id=?""",
            (grant_call_id,),
        ).fetchone()
        if row is None:
            raise KeyError(grant_call_id)

        version_id = str(row[0])
        staged = self.connection.execute(
            """SELECT payload_json
               FROM canonical_staging_items
               WHERE published_entity_id=?
               ORDER BY published_at DESC, id DESC
               LIMIT 1""",
            (version_id,),
        ).fetchone()
        projection_fields: dict[str, object] = {}
        if staged is not None:
            loaded = json.loads(str(staged[0]))
            if isinstance(loaded, dict):
                projection_fields = loaded

        supported = str(projection_fields.get("supported_activities") or "")
        eligible = str(projection_fields.get("eligible_costs") or "")
        supplied_keywords = str(projection_fields.get("keywords") or "")
        fallback_keywords = " ".join(
            value for value in (
                str(row[5] or ""),
                str(row[6] or ""),
                str(row[7] or ""),
            ) if value
        )
        keywords = " ".join(
            value for value in (supplied_keywords, fallback_keywords) if value
        )

        self.connection.execute(
            """DELETE FROM grant_search_documents
               WHERE grant_call_version_id IN (
                 SELECT id FROM grant_call_versions
                 WHERE grant_call_id=? AND id<>?
               )""",
            (grant_call_id, version_id),
        )
        updated_at = (
            now or datetime.now(timezone.utc)
        ).astimezone(timezone.utc).isoformat()
        self.connection.execute(
            """INSERT INTO grant_search_documents(
                 grant_call_version_id,title,summary,supported_activities,
                 eligible_costs,keywords,status,submission_close_at,updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(grant_call_version_id) DO UPDATE SET
                 title=excluded.title,
                 summary=excluded.summary,
                 supported_activities=excluded.supported_activities,
                 eligible_costs=excluded.eligible_costs,
                 keywords=excluded.keywords,
                 status=excluded.status,
                 submission_close_at=excluded.submission_close_at,
                 updated_at=excluded.updated_at""",
            (
                version_id,
                str(row[1]),
                str(row[2]),
                supported,
                eligible,
                keywords,
                str(row[3]),
                row[4],
                updated_at,
            ),
        )
        if commit:
            self.connection.commit()
        return SearchProjectionResult(
            grant_call_id=grant_call_id,
            grant_call_version_id=version_id,
            indexed=True,
        )

    def handle_outbox(
        self,
        event: OutboxEvent,
        *,
        commit: bool = True,
    ) -> None:
        if event.event_type is not OutboxEventType.SEARCH_REINDEX_REQUIRED:
            raise ValueError("search projection received non-search outbox event")
        grant_call_id = str(
            event.payload.get("grantCallId") or event.aggregate_id
        )
        if not grant_call_id:
            raise ValueError("search reindex event has no grantCallId")
        self.reindex_grant_call(grant_call_id, commit=commit)
