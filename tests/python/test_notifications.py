import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for relative in (
    ("packages", "notifications", "src"),
    ("packages", "watches", "src"),
    ("packages", "change-detection", "src"),
    ("packages", "search", "src"),
    ("packages", "eligibility", "src"),
    ("packages", "finance", "src"),
):
    sys.path.insert(0, str(ROOT.joinpath(*relative)))

from dotacni_majak_changes import (
    ChangeEvent,
    ChangeSeverity,
    ChangeType,
)
from dotacni_majak_notifications import (
    DeadlineReminderPlanner,
    InMemoryNotificationRepository,
    NotificationChannel,
    NotificationComposer,
    NotificationDispatcher,
    NotificationOutboxConsumer,
    NotificationStatus,
    PushDeliveryResult,
    WebPushSubscription,
)
from dotacni_majak_search import MatchBand
from dotacni_majak_watches import WatchMatch, WatchMatchStatus


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def watch_match(status=WatchMatchStatus.MATCHED, candidate=True):
    return WatchMatch(
        id="wm1",
        watch_id="w1",
        project_id="p1",
        grant_call_id="g1",
        grant_call_version_id="v2",
        status=status,
        match_band=MatchBand.VERY_GOOD,
        relevance_score=0.9,
        reason_codes=("ONTOLOGY_MATCH",),
        notification_candidate=candidate,
        dedupe_key=f"watch:w1:g1:v2:{status.value}",
    )


class RecordingPushProvider:
    def __init__(self, delivered=True):
        self.delivered = delivered
        self.payloads = []

    def send(self, subscription, payload):
        self.payloads.append((subscription, payload))
        return PushDeliveryResult(
            delivered=self.delivered,
            provider_message_id="m1" if self.delivered else None,
            error_code=None if self.delivered else "TEMPORARY",
        )


class NotificationTest(unittest.TestCase):
    def test_positive_watch_match_creates_in_app_and_opt_in_push(self):
        repo = InMemoryNotificationRepository()
        composer = NotificationComposer()
        request = composer.for_watch_match(
            user_id="u1",
            match=watch_match(),
            web_push_opt_in=True,
        )
        self.assertIsNotNone(request)

        created = NotificationOutboxConsumer(repo).consume(
            request,
            now=NOW,
        )
        self.assertEqual(
            {item.channel for item in created},
            {NotificationChannel.IN_APP, NotificationChannel.WEB_PUSH},
        )

        # Consuming the same logical request again is idempotent.
        repeated = NotificationOutboxConsumer(repo).consume(
            request,
            now=NOW,
        )
        self.assertEqual(
            {item.id for item in created},
            {item.id for item in repeated},
        )

    def test_ineligible_match_creates_no_notification_request(self):
        request = NotificationComposer().for_watch_match(
            user_id="u1",
            match=watch_match(
                status=WatchMatchStatus.NOT_ELIGIBLE,
                candidate=False,
            ),
            web_push_opt_in=True,
        )
        self.assertIsNone(request)

    def test_critical_deadline_change_contains_concrete_diff(self):
        event = ChangeEvent(
            id="chg1",
            grant_call_id="g1",
            from_version_id="v1",
            to_version_id="v2",
            change_type=ChangeType.DEADLINE_CHANGED,
            severity=ChangeSeverity.CRITICAL,
            field_path="deadlines.application_close",
            old_value="2027-01-31",
            new_value="2027-02-28",
            evidence_id="e1",
            created_at=NOW,
        )
        request = NotificationComposer().for_change_event(
            user_id="u1",
            watch_id="w1",
            grant_call_version_id="v2",
            event=event,
            web_push_opt_in=True,
        )
        self.assertIsNotNone(request)
        self.assertIn("2027-01-31", request.body)
        self.assertIn("2027-02-28", request.body)
        self.assertTrue(request.web_push_opt_in)

    def test_editorial_change_is_suppressed(self):
        event = ChangeEvent(
            id="chg2",
            grant_call_id="g1",
            from_version_id="v1",
            to_version_id="v2",
            change_type=ChangeType.OTHER,
            severity=ChangeSeverity.EDITORIAL,
            field_path="title",
            old_value="A",
            new_value="B",
            evidence_id=None,
            created_at=NOW,
        )
        request = NotificationComposer().for_change_event(
            user_id="u1",
            watch_id="w1",
            grant_call_version_id="v2",
            event=event,
            web_push_opt_in=True,
        )
        self.assertIsNone(request)

    def test_deadline_reminders_are_exact_and_deduplicable(self):
        planner = DeadlineReminderPlanner()
        deadline = date(2026, 9, 30)
        self.assertEqual(
            planner.due(
                deadline=deadline,
                today=date(2026, 9, 23),
            ),
            (7,),
        )
        self.assertEqual(
            planner.due(
                deadline=deadline,
                today=date(2026, 9, 23),
                already_sent_offsets={7},
            ),
            (),
        )

    def test_push_failure_does_not_remove_in_app_notification(self):
        repo = InMemoryNotificationRepository()
        request = NotificationComposer().for_watch_match(
            user_id="u1",
            match=watch_match(),
            web_push_opt_in=True,
        )
        created = NotificationOutboxConsumer(repo).consume(
            request,
            now=NOW,
        )
        in_app = next(
            item for item in created
            if item.channel is NotificationChannel.IN_APP
        )
        push = next(
            item for item in created
            if item.channel is NotificationChannel.WEB_PUSH
        )

        provider = RecordingPushProvider(delivered=False)
        dispatcher = NotificationDispatcher(
            repo,
            web_push_provider=provider,
        )
        sent_in_app = dispatcher.dispatch(in_app)
        failed_push = dispatcher.dispatch(
            push,
            subscription=WebPushSubscription(
                id="sub1",
                user_id="u1",
                endpoint_ref="secret-ref-1",
            ),
        )

        self.assertEqual(sent_in_app.status, NotificationStatus.SENT)
        self.assertEqual(failed_push.status, NotificationStatus.FAILED)
        self.assertEqual(len(repo.unread_for_user("u1")), 1)


if __name__ == "__main__":
    unittest.main()
