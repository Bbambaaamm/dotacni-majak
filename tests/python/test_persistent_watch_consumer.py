"""Regression tests for the offline published-call watch consumer (#509)."""
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for relative in ("pipelines/ingestion/src", "packages/watches/src", "packages/notifications/src",
                 "packages/search/src", "packages/eligibility/src", "packages/finance/src"):
    sys.path.insert(0, str(ROOT / relative))

from dotacni_majak_ingestion.outbox import OutboxEventType, OutboxStatus
from dotacni_majak_ingestion.sqlite_outbox import SqliteOutboxRepository
from dotacni_majak_search import MatchBand
from dotacni_majak_watches.persistent import PersistentProjectWatchConsumer


class PersistentWatchConsumerTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.db.executescript(path.read_text(encoding="utf-8"))
        self.consumer = PersistentProjectWatchConsumer(self.db)

    def tearDown(self):
        self.db.close()

    def seed_call(self):
        self.db.execute("INSERT INTO providers(id,name,provider_type) VALUES ('p','Provider','NATIONAL')")
        self.db.execute("""INSERT INTO programmes(id,provider_id,name,funding_origin)
            VALUES ('prog','p','Programme','CZ_NATIONAL')""")
        self.db.execute("""INSERT INTO grant_calls
            (id,programme_id,canonical_slug,current_version_id,current_status,current_title,
             first_seen_at,created_at,updated_at)
            VALUES ('call','prog','call',NULL,'OPEN','Call','now','now','now')""")
        for index in (1, 2):
            self.db.execute("""INSERT INTO grant_call_versions
                (id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at)
                VALUES (?,?,?,?,?,'OPEN','VERIFIED','now')""",
                (f'v{index}', 'call', index, 'now', 'Call'))
        self.db.execute("UPDATE grant_calls SET current_version_id='v2' WHERE id='call'")
        self.db.execute("""INSERT INTO source_registry
            (id,code,name,base_url,adapter_key,authority,retrieval_mode,refresh_minutes)
            VALUES ('src','SOURCE','Source','https://example.invalid/','test','OFFICIAL','JSON',60)""")
        self.db.execute("""INSERT INTO source_records
            (id,source_id,external_id,canonical_url,record_type,grant_call_id,first_seen_at,last_seen_at)
            VALUES ('record','src','external','https://example.invalid/','GRANT_CALL','call','now','now')""")
        self.db.execute("""INSERT INTO grant_search_documents
            (grant_call_version_id,title,status,updated_at) VALUES ('v2','tenis','OPEN','now')""")
        self.db.commit()

    def test_superseded_event_is_acknowledged_before_current_publication(self):
        self.seed_call()
        repo = SqliteOutboxRepository(self.db)
        for version in ('v1', 'v2'):
            repo.enqueue(event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
                aggregate_type='GRANT_CALL', aggregate_id='call',
                payload={'grantCallId': 'call', 'grantCallVersionId': version,
                         'sourceCode': 'SOURCE'}, dedupe_key=f'publication:{version}')
        self.assertEqual(self.consumer.drain(), ['DELIVERED', 'DELIVERED'])
        self.assertEqual([repo.get_by_dedupe_key(f'publication:{v}').status
                          for v in ('v1', 'v2')],
                         [OutboxStatus.DELIVERED, OutboxStatus.DELIVERED])

    def test_each_activation_enqueues_fresh_reevaluation(self):
        self.seed_call()
        self.db.execute("""INSERT INTO projects(id,natural_language_intent,currency_code,created_at,updated_at)
            VALUES ('project','tenis rekonstrukce kurty','CZK','now','now')""")
        self.db.execute("""INSERT INTO watches
            (id,watch_type,project_id,minimum_match_band,created_at,updated_at)
            VALUES ('watch','PROJECT','project','POSSIBLE','now','now')""")
        payload = {'grantCallId': 'call', 'grantCallVersionId': 'v2', 'sourceCode': 'SOURCE'}
        self.consumer._published(payload, activation_id='activation-1')
        self.db.execute("""UPDATE grant_search_documents SET title='tenis rekonstrukce kurty'
            WHERE grant_call_version_id='v2'""")
        self.consumer._published(payload, activation_id='activation-2')
        keys = [row[0] for row in self.db.execute("""SELECT dedupe_key FROM outbox_events
            WHERE event_type='WATCH_REEVALUATION_REQUIRED' ORDER BY dedupe_key""")]
        self.assertEqual(keys, [
            'watch-reevaluate:watch:v2:activation-1',
            'watch-reevaluate:watch:v2:activation-2',
        ])

    def test_reclaimed_lease_has_distinct_owner(self):
        other = PersistentProjectWatchConsumer(self.db)
        self.assertNotEqual(self.consumer.worker_id, other.worker_id)
        repo = SqliteOutboxRepository(self.db)
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        repo.enqueue(event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type='GRANT_CALL', aggregate_id='missing', payload={},
            dedupe_key='lease-fencing', now=past)
        stale = repo.claim_by_dedupe_key('lease-fencing', worker_id=self.consumer.worker_id,
                                         now=past, lease_seconds=1)
        replacement = repo.claim_by_dedupe_key('lease-fencing', worker_id=other.worker_id)
        self.assertEqual(replacement.lease_owner, other.worker_id)
        from dotacni_majak_ingestion.sqlite_outbox import OutboxLeaseError
        with self.assertRaises(OutboxLeaseError):
            repo.mark_delivered(stale.id, worker_id=self.consumer.worker_id)
        self.assertEqual(repo.get(stale.id).status, OutboxStatus.PROCESSING)

    def test_partial_fts_hit_is_weak_not_a_possible_alert(self):
        self.db.execute("""INSERT INTO grant_search_fts
            (grant_call_version_id,title,summary,supported_activities,eligible_costs,keywords)
            VALUES ('v1','tenis','','','','')""")
        weak = self.consumer._relevance("tenis rekonstrukce kurty", "v1")
        self.assertIsNotNone(weak)
        self.assertEqual(weak.match_band, MatchBand.WEAK)
        self.assertLess(weak.relevance_score, 0.35)
        self.assertIsNone(self.consumer._relevance("fotovoltaika", "v1"))
        self.db.execute("""INSERT INTO grant_search_fts
            (grant_call_version_id,title,summary,supported_activities,eligible_costs,keywords)
            VALUES ('v2','tenis rekonstrukce kurty','','','','')""")
        self.assertEqual(
            self.consumer._relevance("tenis rekonstrukce kurty", "v2").match_band,
            MatchBand.POSSIBLE,
        )

    def test_expired_processing_claim_is_recovered(self):
        repo = SqliteOutboxRepository(self.db)
        now = datetime.now(timezone.utc)
        event = repo.enqueue(
            event_type=OutboxEventType.CHANGE_DETECTION_REQUIRED,
            aggregate_type="GRANT_CALL", aggregate_id="missing",
            payload={"grantCallId": "missing", "grantCallVersionId": "missing", "sourceCode": "none"},
            dedupe_key="watch-recover-test", now=now - timedelta(minutes=2),
        )
        claim = repo.claim_by_dedupe_key(
            event.dedupe_key, worker_id="crashed-worker", now=now - timedelta(minutes=2),
            lease_seconds=1,
        )
        self.assertEqual(claim.status, OutboxStatus.PROCESSING)
        self.assertEqual(self.consumer.drain(), ["FAILED"])
        recovered = repo.get(event.id)
        self.assertEqual(recovered.status, OutboxStatus.FAILED)
        self.assertEqual(recovered.attempts, 2)


if __name__ == "__main__":
    unittest.main()
