"""D1-compatible SQLite consumer for published-call Project Watch events.

Run outside the Worker against the same database as canonical publication. No
source failure or search-index failure is interpreted as a negative match.
"""
from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from uuid import uuid4
from datetime import datetime, timezone

from dotacni_majak_ingestion.outbox import OutboxEventType
from dotacni_majak_ingestion.sqlite_outbox import OutboxLeaseError, SqliteOutboxRepository
from dotacni_majak_notifications import NotificationComposer
from dotacni_majak_search import (
    HybridRanker, HybridSignals, MatchBand, RankedGrantMatch, build_fts_query,
)
from .matcher import CandidateEvaluation, ProjectWatch, ProjectWatchMatcher, WatchMatch, WatchMatchStatus


class PersistentProjectWatchConsumer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection
        self.db.execute("PRAGMA foreign_keys = ON")
        self.outbox = SqliteOutboxRepository(connection)
        self.worker_id = f"project-watch-{uuid4().hex}"

    def drain(self) -> list[str]:
        """Process only watch-related outbox events; other consumers retain theirs."""
        statuses: list[str] = []
        while True:
            row = self.db.execute(
                """SELECT dedupe_key FROM outbox_events
                   WHERE event_type IN ('CHANGE_DETECTION_REQUIRED',
                       'WATCH_REEVALUATION_REQUIRED', 'NOTIFICATION_REQUIRED')
                     AND dead_lettered_at IS NULL
                     AND ((status IN ('PENDING','FAILED') AND available_at <= ?)
                       OR (status='PROCESSING' AND lease_expires_at IS NOT NULL
                           AND lease_expires_at <= ?))
                   ORDER BY available_at, created_at, id LIMIT 1""",
                (datetime.now(timezone.utc).isoformat(),) * 2,
            ).fetchone()
            if row is None:
                return statuses
            event = self.outbox.claim_by_dedupe_key(row[0], worker_id=self.worker_id)
            if event is None:
                return statuses
            try:
                self.db.execute("BEGIN IMMEDIATE")
                if event.event_type is OutboxEventType.CHANGE_DETECTION_REQUIRED:
                    self._published(event.payload, activation_id=event.id)
                elif event.event_type is OutboxEventType.WATCH_REEVALUATION_REQUIRED:
                    self._reevaluate(event.payload)
                else:
                    self._notify(event.payload)
                self.outbox.mark_delivered(event.id, worker_id=self.worker_id, commit=False)
                self.db.commit()
                statuses.append("DELIVERED")
            except Exception as exc:
                self.db.rollback()
                try:
                    self.outbox.mark_failed(event.id, worker_id=self.worker_id, error=exc)
                except OutboxLeaseError:
                    # Another instance reclaimed an expired lease: never mutate
                    # its state or acknowledge its work under the stale owner.
                    statuses.append("LEASE_LOST")
                    return statuses
                statuses.append("FAILED")
                return statuses  # no retry loop on the same broken event

    def _published(self, payload: dict, *, activation_id: str) -> None:
        call_id = payload["grantCallId"]
        version_id = payload["grantCallVersionId"]
        current = self.db.execute(
            "SELECT current_version_id FROM grant_calls WHERE id=?", (call_id,)
        ).fetchone()
        if current is not None and current[0] != version_id:
            return  # obsolete activation: retry cannot make it current again
        row = self.db.execute(
            """SELECT v.status, s.authority FROM grant_call_versions v
               JOIN grant_calls g ON g.current_version_id=v.id
               JOIN source_records r ON r.grant_call_id=g.id
               JOIN source_registry s ON s.id=r.source_id
               JOIN grant_search_documents d ON d.grant_call_version_id=v.id
               WHERE v.id=? AND g.id=? AND s.code=? AND s.authority='OFFICIAL'
               LIMIT 1""",
            (version_id, call_id, payload["sourceCode"]),
        ).fetchone()
        if row is None:
            raise ValueError("published official current searchable version unavailable")
        if row[0] not in ("OPEN", "PLANNED", "ANNOUNCED"):
            return
        for watch_id, intent in self.db.execute(
            """SELECT w.id, p.natural_language_intent FROM watches w
               JOIN projects p ON p.id=w.project_id
               WHERE w.watch_type='PROJECT' AND w.enabled=1"""
        ).fetchall():
            if self._relevance(intent, version_id) is not None:
                self.outbox.enqueue(
                    event_type=OutboxEventType.WATCH_REEVALUATION_REQUIRED,
                    aggregate_type="WATCH", aggregate_id=watch_id,
                    payload={"watchId": watch_id, "grantCallId": call_id,
                             "grantCallVersionId": version_id},
                    dedupe_key=f"watch-reevaluate:{watch_id}:{version_id}:{activation_id}",
                    commit=False,
                )

    def _relevance(self, intent: str, version_id: str) -> RankedGrantMatch | None:
        # Each token is generated by the safe FTS query builder. Partial hits are
        # weak unless enough of the actual intent is covered; no invented score.
        tokens = re.findall(r'"[^\"]+"\*?', build_fts_query(intent, prefix=True))[:20]
        if not tokens:
            return None
        hits = sum(bool(self.db.execute(
            """SELECT 1 FROM grant_search_fts WHERE grant_search_fts MATCH ?
               AND grant_call_version_id=? LIMIT 1""", (token, version_id),
        ).fetchone()) for token in tokens)
        if not hits:
            return None
        return HybridRanker().rank([HybridSignals(
            grant_call_version_id=version_id, lexical_relevance=hits / len(tokens),
        )])[0]

    def _reevaluate(self, payload: dict) -> None:
        row = self.db.execute(
            """SELECT w.project_id,w.enabled,w.minimum_match_band,g.current_version_id,
                      p.natural_language_intent
               FROM watches w JOIN grant_calls g ON g.id=?
               JOIN projects p ON p.id=w.project_id
               WHERE w.id=? AND w.watch_type='PROJECT'""",
            (payload["grantCallId"], payload["watchId"]),
        ).fetchone()
        if row is None or row[3] != payload["grantCallVersionId"]:
            return  # deleted watch or superseded publication
        watch = ProjectWatch(payload["watchId"], row[0], bool(row[1]), MatchBand(row[2] or "POSSIBLE"))
        if not watch.enabled:
            return
        version = payload["grantCallVersionId"]
        relevance = self._relevance(row[4], version)
        if relevance is None:
            return
        match = ProjectWatchMatcher().reevaluate(
            watch, CandidateEvaluation(payload["grantCallId"], version, relevance, None, None)
        ).match
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT OR IGNORE INTO watch_matches(
               id,watch_id,project_id,grant_call_id,grant_call_version_id,status,
               match_band,relevance_score_ppm,reason_codes_json,notification_candidate,
               dedupe_key,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (match.id, match.watch_id, match.project_id, match.grant_call_id, version,
             match.status.value, match.match_band.value, round(match.relevance_score*1000000),
             json.dumps(match.reason_codes), int(match.notification_candidate),
             match.dedupe_key, now, now),
        )
        if match.notification_candidate:
            self.outbox.enqueue(
                event_type=OutboxEventType.NOTIFICATION_REQUIRED,
                aggregate_type="WATCH_MATCH", aggregate_id=match.id,
                payload={"matchId": match.id},
                dedupe_key=f"notify:{match.dedupe_key}", commit=False,
            )

    def _notify(self, payload: dict) -> None:
        row = self.db.execute(
            """SELECT m.watch_id,m.grant_call_version_id,m.status,m.dedupe_key,
                      p.owner_user_id,w.enabled,g.current_version_id,
                      m.match_band,m.relevance_score_ppm
               FROM watch_matches m JOIN watches w ON w.id=m.watch_id
               JOIN projects p ON p.id=w.project_id
               JOIN grant_calls g ON g.id=m.grant_call_id
               WHERE m.id=? AND m.notification_candidate=1""",
            (payload["matchId"],),
        ).fetchone()
        if row is None or not row[5] or row[1] != row[6]:
            return
        # Composer supplies truthful NEEDS_INFORMATION wording and dedupe policy.
        match = WatchMatch(payload["matchId"], row[0], "", "", row[1],
                           WatchMatchStatus(row[2]), MatchBand(row[7]), row[8] / 1000000,
                           (), True, row[3])
        request = NotificationComposer().for_watch_match(
            user_id=row[4], match=match, web_push_opt_in=False,
        )
        if request is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT OR IGNORE INTO notifications(
               id,user_id,watch_id,grant_call_version_id,change_event_id,
               notification_type,channel,severity,title,body,dedupe_key,status,
               created_at,sent_at) VALUES (?,?,?,?,NULL,?,'IN_APP',?,?,?,?,'SENT',?,?)""",
            ("ntf_" + hashlib.sha256(
                (request.dedupe_base + ":channel:IN_APP").encode()).hexdigest()[:24],
             request.user_id, request.watch_id, request.grant_call_version_id,
             request.notification_type.value, request.severity.value,
             request.title, request.body, request.dedupe_base + ":channel:IN_APP", now, now),
        )
