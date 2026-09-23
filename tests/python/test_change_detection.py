import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "change-detection" / "src"))

from dotacni_majak_changes import (
    ChangeDetector,
    ChangeSeverity,
    ChangeType,
    FundingState,
    GrantVersionState,
    RequirementState,
)


AT = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


class ChangeDetectorTest(unittest.TestCase):
    def setUp(self):
        self.detector = ChangeDetector()

    def detect(self, old, new):
        return self.detector.detect(
            grant_call_id="g1",
            from_version_id="v1",
            to_version_id="v2",
            old=old,
            new=new,
            created_at=AT,
        )

    def test_deadline_diff_is_concrete_and_critical(self):
        events = self.detect(
            GrantVersionState(
                status="OPEN",
                title="Call",
                submission_close_at="2027-01-31T23:59:59+01:00",
            ),
            GrantVersionState(
                status="OPEN",
                title="Call",
                submission_close_at="2027-02-28T23:59:59+01:00",
                evidence_by_field={
                    "deadlines.application_close": "e-new-deadline"
                },
            ),
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.change_type, ChangeType.DEADLINE_CHANGED)
        self.assertEqual(event.severity, ChangeSeverity.CRITICAL)
        self.assertEqual(event.field_path, "deadlines.application_close")
        self.assertEqual(
            event.old_value,
            "2027-01-31T23:59:59+01:00",
        )
        self.assertEqual(
            event.new_value,
            "2027-02-28T23:59:59+01:00",
        )
        self.assertEqual(event.evidence_id, "e-new-deadline")

    def test_support_rate_change_is_critical(self):
        events = self.detect(
            GrantVersionState(
                status="OPEN",
                title="Call",
                funding={
                    "municipality": FundingState(
                        support_rate_max_bps=9000
                    )
                },
            ),
            GrantVersionState(
                status="OPEN",
                title="Call",
                funding={
                    "municipality": FundingState(
                        support_rate_max_bps=8000
                    )
                },
            ),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].change_type, ChangeType.FUNDING_CHANGED)
        self.assertEqual(events[0].severity, ChangeSeverity.CRITICAL)
        self.assertEqual(
            events[0].field_path,
            "funding.municipality.support_rate_max_bps",
        )
        self.assertEqual((events[0].old_value, events[0].new_value), (9000, 8000))

    def test_project_budget_limit_has_budget_change_type(self):
        events = self.detect(
            GrantVersionState(
                status="OPEN",
                title="Call",
                funding={
                    "default": FundingState(
                        project_cost_max_minor=1_000_000
                    )
                },
            ),
            GrantVersionState(
                status="OPEN",
                title="Call",
                funding={
                    "default": FundingState(
                        project_cost_max_minor=900_000
                    )
                },
            ),
        )
        self.assertEqual(events[0].change_type, ChangeType.BUDGET_CHANGED)
        self.assertEqual(events[0].severity, ChangeSeverity.CRITICAL)

    def test_pause_is_critical_status_change(self):
        events = self.detect(
            GrantVersionState(status="OPEN", title="Call"),
            GrantVersionState(status="PAUSED", title="Call"),
        )
        self.assertEqual(events[0].change_type, ChangeType.STATUS_CHANGED)
        self.assertEqual(events[0].severity, ChangeSeverity.CRITICAL)

    def test_requirement_add_is_important(self):
        requirement = RequirementState(
            title="Položkový rozpočet",
            necessity="REQUIRED",
            requirement_type="DOCUMENT",
        )
        events = self.detect(
            GrantVersionState(status="OPEN", title="Call"),
            GrantVersionState(
                status="OPEN",
                title="Call",
                requirements={"budget": requirement},
            ),
        )
        self.assertEqual(events[0].change_type, ChangeType.REQUIREMENT_CHANGED)
        self.assertEqual(events[0].severity, ChangeSeverity.IMPORTANT)
        self.assertIsNone(events[0].old_value)
        self.assertEqual(events[0].new_value["title"], "Položkový rozpočet")

    def test_document_hash_change_is_informational(self):
        events = self.detect(
            GrantVersionState(
                status="OPEN",
                title="Call",
                documents={"conditions": "sha-old"},
            ),
            GrantVersionState(
                status="OPEN",
                title="Call",
                documents={"conditions": "sha-new"},
            ),
        )
        self.assertEqual(events[0].change_type, ChangeType.DOCUMENT_CHANGED)
        self.assertEqual(events[0].severity, ChangeSeverity.INFORMATIONAL)

    def test_title_only_change_is_editorial(self):
        events = self.detect(
            GrantVersionState(status="OPEN", title="Původní název"),
            GrantVersionState(status="OPEN", title="Nový název"),
        )
        self.assertEqual(events[0].change_type, ChangeType.OTHER)
        self.assertEqual(events[0].severity, ChangeSeverity.EDITORIAL)

    def test_identical_versions_create_no_events(self):
        state = GrantVersionState(
            status="OPEN",
            title="Call",
            supported_activities=frozenset({"SPORT"}),
        )
        self.assertEqual(self.detect(state, state), ())

    def test_event_ids_are_deterministic(self):
        old = GrantVersionState(status="OPEN", title="A")
        new = GrantVersionState(status="OPEN", title="B")
        first = self.detect(old, new)
        second = self.detect(old, new)
        self.assertEqual(first[0].id, second[0].id)


if __name__ == "__main__":
    unittest.main()
