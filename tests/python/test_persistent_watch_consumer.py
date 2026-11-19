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
