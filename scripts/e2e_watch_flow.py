"""Local browser E2E driver: simulated official record through trusted publisher.

Only operates on the isolated Wrangler e2e database; never fetches or claims a
real source. Failure mode injects an invalid publication event (no canonical
mutation) to verify last-known-good notification and call remain available.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import replace
from types import ModuleType
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in ("pipelines/ingestion/src", "packages/source-sdk/src", "packages/watches/src",
                 "packages/notifications/src", "packages/search/src",
                 "packages/eligibility/src", "packages/finance/src",
                 "packages/change-detection/src"):
    sys.path.insert(0, str(ROOT / relative))

# Import the ingestion submodules directly: its package __init__ eagerly loads
# live HTTP adapter dependencies not needed by this offline SQLite E2E.
ingestion_package = ModuleType("dotacni_majak_ingestion")
ingestion_package.__path__ = [str(ROOT / "pipelines/ingestion/src/dotacni_majak_ingestion")]
sys.modules["dotacni_majak_ingestion"] = ingestion_package

from dotacni_majak_ingestion.local_publish import SearchableGrant
from dotacni_majak_ingestion.outbox import OutboxEventType
from dotacni_majak_ingestion.search_projection import SqliteSearchProjection
from dotacni_majak_ingestion.snapshot import LocalRawSnapshotStore
from dotacni_majak_ingestion.sqlite_outbox import SqliteOutboxRepository
from dotacni_majak_ingestion.trusted_ingest import TrustedGrantIngestor
from local_trusted_publish import discover_local_d1_database
from dotacni_majak_watches.persistent import PersistentProjectWatchConsumer
from dotacni_majak_changes import ChangeDetector, GrantVersionState

SOURCE_URL = "https://example.invalid/e2e/tennis-official-simulation"
CALL_ID = "grant:e2e:tennis-new"
NOW = datetime.now(timezone.utc)


def publish(db: sqlite3.Connection, *, simulate_failure: bool = False) -> None:
    # Fixture content is stored first as immutable RAW; trusted staging and
    # canonical publisher create evidence and transactional outbox events.
    content = json.dumps({"title": "E2E nová výzva — rekonstrukce tenisových kurtů",
                          "status": "OPEN", "source": "SIMULATED_OFFICIAL_E2E"},
                         ensure_ascii=False).encode()
    snapshot = LocalRawSnapshotStore(ROOT / ".local" / "e2e-raw").put(
        source_code="E2E_TEST", source_url=SOURCE_URL,
        content=content, mime_type="application/json", retrieved_at=NOW,
    )
    grant = SearchableGrant(
        source_id="e2e-source-tennis-new", source_code="E2E_TEST",
        source_name="Simulovaný oficiální zdroj E2E", source_base_url="https://example.invalid/",
        adapter_key="e2e-simulated", source_external_id="E2E-TENNIS-NEW",
        source_url=SOURCE_URL, content_hash=snapshot.sha256,
        provider_id="e2e-provider-tennis", provider_name="E2E test provider tennis",
        provider_type="NATIONAL", programme_id="e2e-programme-tennis",
        programme_name="E2E tenis", funding_origin="CZ_NATIONAL",
        grant_call_id=CALL_ID, grant_version_id="gcv-e2e-tennis-new",
        canonical_slug="e2e-tennis-new", title="E2E nová výzva — rekonstrukce tenisových kurtů",
        summary="Simulovaná nová výzva pro integrační ověření, nikoli skutečná dotace.",
        status="OPEN", verification_status="AUTO_EXTRACTED",
        captured_at=NOW.isoformat(), raw_snapshot_id=snapshot.snapshot_id,
        supported_activities="rekonstrukce tenisových kurtů", keywords="tenis kurty rekonstrukce",
        retrieval_mode="JSON",
    )
    if simulate_failure:
        before = db.execute(
            "SELECT current_version_id FROM grant_calls WHERE id=?", (CALL_ID,)
        ).fetchone()
        outbox_before = db.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]
        notification_before = db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        if before is None:
            raise RuntimeError("last-known-good call missing before failed refresh")
        try:
            TrustedGrantIngestor(db).ingest(
                replace(grant, content_hash="0" * 64), record_snapshot=snapshot, now=NOW,
            )
        except ValueError as exc:
            if "hash does not match content_hash" not in str(exc):
                raise
        else:
            raise AssertionError("invalid source hash unexpectedly accepted")
        after = db.execute(
            "SELECT current_version_id FROM grant_calls WHERE id=?", (CALL_ID,)
        ).fetchone()
        assert after is not None and after[0] == before[0]
        assert db.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0] == outbox_before
        assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == notification_before
        print("SIMULATED_SOURCE_FAILURE_LAST_GOOD_PRESERVED")
        return
    result = TrustedGrantIngestor(db).ingest(grant, record_snapshot=snapshot, now=NOW)
    outbox = SqliteOutboxRepository(db)
    projection = SqliteSearchProjection(db)
    for key in result.publication.outbox_dedupe_keys:
        event = outbox.get_by_dedupe_key(key)
        if event and event.event_type is OutboxEventType.SEARCH_REINDEX_REQUIRED:
            claimed = outbox.claim_by_dedupe_key(key, worker_id="e2e-search")
            if claimed:
                projection.handle_outbox(claimed)
                outbox.mark_delivered(claimed.id, worker_id="e2e-search")
    print("PUBLISHED", result.publication.grant_call_version_id)


def update_version(db: sqlite3.Connection, *, simulate_failure: bool = False) -> None:
    """Publish a second version for a workspace's call through RAW-first staging."""
    source_url = "https://example.invalid/e2e/open"
    now = datetime.now(timezone.utc)
    content = json.dumps({"title": "E2E otevřená výzva — digitalizace obce",
                          "deadline": "2028-01-31T23:59:59Z", "source": "SIMULATED_E2E"},
                         ensure_ascii=False).encode()
    snapshot = LocalRawSnapshotStore(ROOT / ".local" / "e2e-raw").put(
        source_code="E2E_A", source_url=source_url, content=content,
        mime_type="application/json", retrieved_at=now,
    )
    grant = SearchableGrant(
        source_id="e2e-source-open", source_code="E2E_A", source_name="E2E oficiální zdroj A",
        source_base_url="https://example.invalid/", adapter_key="e2e-a",
        source_external_id="E2E-OPEN", source_url=source_url,
        content_hash=snapshot.sha256, provider_id="e2e-provider-open",
        provider_name="E2E test provider A", provider_type="NATIONAL",
        programme_id="e2e-programme-open", programme_name="E2E Digitalizace A",
        funding_origin="CZ_NATIONAL", grant_call_id="grant:e2e:open",
        grant_version_id="gcv-e2e-open-v2", canonical_slug="e2e-open-digitalizace",
        title="E2E otevřená výzva — digitalizace obce",
        summary="Simulované prodloužení termínu pro E2E ověření.",
        status="OPEN", verification_status="AUTO_EXTRACTED",
        captured_at=now.isoformat(), raw_snapshot_id=snapshot.snapshot_id,
        published_at="2026-09-20T08:00:00Z", submission_open_at="2026-09-20T08:00:00Z",
        submission_close_at="2028-01-31T23:59:59Z", retrieval_mode="JSON",
        supported_activities="digitalizace obce", keywords="digitalizace obce e2e",
    )
    before = db.execute("SELECT current_version_id FROM grant_calls WHERE id='grant:e2e:open'").fetchone()[0]
    if simulate_failure:
        try:
            TrustedGrantIngestor(db).ingest(replace(grant, content_hash="0" * 64, raw_snapshot_id=None),
                                            record_snapshot=snapshot, now=now)
        except ValueError as exc:
            if "hash does not match" not in str(exc):
                raise
        else:
            raise AssertionError("invalid RAW hash accepted")
        assert db.execute("SELECT current_version_id FROM grant_calls WHERE id='grant:e2e:open'").fetchone()[0] == before
        print("WORKSPACE_FAILED_RAW_LAST_GOOD_PRESERVED")
        return
    result = TrustedGrantIngestor(db).ingest(grant, record_snapshot=snapshot, now=now)
    def state(version_id: str) -> GrantVersionState:
        row = db.execute("SELECT status,title,summary,submission_open_at,submission_close_at "
                         "FROM grant_call_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            raise AssertionError("published version missing")
        field_paths = {"/submission_close_at": "deadlines.application_close",
                       "/status": "status", "/title": "title", "/summary": "summary"}
        evidence = db.execute(
            "SELECT fe.id,fe.field_path FROM field_evidence fe "
            "WHERE fe.entity_id=? AND fe.field_path IN ('/submission_close_at','/status','/title','/summary') "
            "ORDER BY fe.created_at DESC,fe.id DESC", (version_id,)
        ).fetchall()
        evidence_by_field = {field_paths[path]: evidence_id for evidence_id, path in evidence
                             if path in field_paths}
        return GrantVersionState(status=row[0], title=row[1], summary=row[2],
                                 submission_open_at=row[3], submission_close_at=row[4],
                                 evidence_by_field=evidence_by_field)
    events = ChangeDetector().detect(
        grant_call_id="grant:e2e:open", from_version_id=before,
        to_version_id=result.publication.grant_call_version_id,
        old=state(before), new=state(result.publication.grant_call_version_id),
        created_at=now,
    )
    for event in events:
        db.execute("INSERT OR IGNORE INTO change_events "
                   "(id,grant_call_id,from_version_id,to_version_id,change_type,severity,field_path,old_value_json,new_value_json,evidence_id,created_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (event.id, event.grant_call_id, event.from_version_id,
                    event.to_version_id, event.change_type.value, event.severity.value,
                    event.field_path, json.dumps(event.old_value), json.dumps(event.new_value),
                    event.evidence_id, event.created_at.isoformat()))
    deadline_provenance = db.execute(
        "SELECT fe.id,dv.sha256,sd.source_url FROM change_events ce "
        "JOIN field_evidence fe ON fe.id=ce.evidence_id "
        "JOIN document_versions dv ON dv.id=fe.document_version_id "
        "JOIN source_documents sd ON sd.id=dv.source_document_id "
        "WHERE ce.from_version_id=? AND ce.to_version_id=? "
        "AND ce.field_path='deadlines.application_close'",
        (before, result.publication.grant_call_version_id),
    ).fetchone()
    assert deadline_provenance is not None and deadline_provenance[1:] == (snapshot.sha256, source_url)
    print("WORKSPACE_VERSION_PUBLISHED", result.publication.grant_call_version_id,
          "CHANGE_EVENTS", len(events), "RAW_EVIDENCE_VERIFIED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("publish", "drain", "fail", "workspace-update", "workspace-fail"))
    args = parser.parse_args()
    path = discover_local_d1_database(ROOT / ".wrangler" / "e2e")
    with sqlite3.connect(path, timeout=10) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if args.action == "publish":
            publish(db)
        elif args.action == "fail":
            publish(db, simulate_failure=True)
        elif args.action == "workspace-update":
            update_version(db)
        elif args.action == "workspace-fail":
            update_version(db, simulate_failure=True)
        else:
            statuses = PersistentProjectWatchConsumer(db).drain()
            print("WATCH_OUTBOX", json.dumps(statuses))


if __name__ == "__main__":
    main()
