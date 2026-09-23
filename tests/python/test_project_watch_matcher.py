import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for relative in (
    ("packages", "watches", "src"),
    ("packages", "search", "src"),
    ("packages", "eligibility", "src"),
    ("packages", "finance", "src"),
):
    sys.path.insert(0, str(ROOT.joinpath(*relative)))

from dotacni_majak_eligibility import EligibilityStatus
from dotacni_majak_finance import FinanceStatus
from dotacni_majak_search import (
    MatchBand,
    MatchReasonCode,
    RankedGrantMatch,
)
from dotacni_majak_watches import (
    CandidateEvaluation,
    ProjectWatch,
    ProjectWatchMatcher,
    WatchMatchAction,
    WatchMatchStatus,
)


def candidate(
    *,
    version="v1",
    call="g1",
    band=MatchBand.VERY_GOOD,
    eligibility=EligibilityStatus.ELIGIBLE,
    finance=FinanceStatus.COMPLETE,
):
    return CandidateEvaluation(
        grant_call_id=call,
        grant_call_version_id=version,
        relevance=RankedGrantMatch(
            grant_call_version_id=version,
            relevance_score=0.91 if band is MatchBand.VERY_GOOD else 0.55,
            match_band=band,
            reasons=(MatchReasonCode.ONTOLOGY_MATCH,),
        ),
        eligibility_status=eligibility,
        finance_status=finance,
    )


class ProjectWatchMatcherTest(unittest.TestCase):
    def setUp(self):
        self.matcher = ProjectWatchMatcher()
        self.watch = ProjectWatch(id="w1", project_id="p1")

    def test_verified_eligible_candidate_is_positive_match(self):
        result = self.matcher.reevaluate(
            self.watch,
            candidate(),
        )
        self.assertEqual(result.action, WatchMatchAction.CREATED)
        self.assertEqual(result.match.status, WatchMatchStatus.MATCHED)
        self.assertTrue(result.match.notification_candidate)

    def test_unknown_eligibility_is_not_presented_as_confirmed_match(self):
        result = self.matcher.reevaluate(
            self.watch,
            candidate(eligibility=EligibilityStatus.NEEDS_INFORMATION),
        )
        self.assertEqual(
            result.match.status,
            WatchMatchStatus.NEEDS_INFORMATION,
        )
        self.assertTrue(result.match.notification_candidate)
        self.assertIn(
            "ELIGIBILITY_NEEDS_INFORMATION",
            result.match.reason_codes,
        )

    def test_verified_ineligible_is_suppressed_as_positive_notification(self):
        result = self.matcher.reevaluate(
            self.watch,
            candidate(eligibility=EligibilityStatus.INELIGIBLE),
        )
        self.assertEqual(
            result.match.status,
            WatchMatchStatus.NOT_ELIGIBLE,
        )
        self.assertFalse(result.match.notification_candidate)

    def test_finance_not_applicable_is_not_positive_match(self):
        result = self.matcher.reevaluate(
            self.watch,
            candidate(finance=FinanceStatus.SCENARIO_NOT_APPLICABLE),
        )
        self.assertEqual(
            result.match.status,
            WatchMatchStatus.NOT_FINANCIALLY_COMPATIBLE,
        )
        self.assertFalse(result.match.notification_candidate)

    def test_unsupported_finance_instrument_requires_review_not_rejection(self):
        result = self.matcher.reevaluate(
            self.watch,
            candidate(finance=FinanceStatus.INSTRUMENT_NOT_SUPPORTED),
        )
        self.assertEqual(
            result.match.status,
            WatchMatchStatus.NEEDS_REVIEW,
        )
        self.assertFalse(result.match.notification_candidate)
        self.assertIn(
            "FINANCE_INSTRUMENT_NOT_SUPPORTED",
            result.match.reason_codes,
        )

    def test_weak_relevance_is_not_a_match(self):
        result = self.matcher.reevaluate(
            self.watch,
            candidate(band=MatchBand.WEAK),
        )
        self.assertEqual(
            result.match.status,
            WatchMatchStatus.NOT_RELEVANT,
        )
        self.assertFalse(result.match.notification_candidate)

    def test_same_version_and_status_is_idempotent(self):
        first = self.matcher.reevaluate(self.watch, candidate())
        second = self.matcher.reevaluate(self.watch, candidate())

        self.assertEqual(first.action, WatchMatchAction.CREATED)
        self.assertEqual(second.action, WatchMatchAction.UNCHANGED)
        self.assertEqual(first.match.id, second.match.id)

    def test_new_version_updates_existing_watch_match(self):
        first = self.matcher.reevaluate(self.watch, candidate(version="v1"))
        second = self.matcher.reevaluate(
            self.watch,
            candidate(
                version="v2",
                eligibility=EligibilityStatus.NEEDS_INFORMATION,
            ),
        )
        self.assertEqual(first.action, WatchMatchAction.CREATED)
        self.assertEqual(second.action, WatchMatchAction.UPDATED)
        self.assertNotEqual(first.match.id, second.match.id)


if __name__ == "__main__":
    unittest.main()
