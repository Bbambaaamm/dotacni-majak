import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "eligibility" / "src"))

from dotacni_majak_eligibility import (
    AttributeDataType,
    AttributeDefinition,
    CompletenessStatus,
    ConditionOperator,
    ConditionResult,
    EligibilityEvaluator,
    EligibilityStatus,
    GroupOperator,
    KNOWN_ABSENT,
    RuleCondition,
    RuleGroup,
    RuleSet,
    UnknownPolicy,
    VerificationStatus,
)


POPULATION = AttributeDefinition(
    "population",
    "applicant.municipality.population",
    AttributeDataType.INTEGER,
)
APPLICANT_TYPE = AttributeDefinition(
    "type",
    "applicant.type",
    AttributeDataType.ENUM,
)
OWNERSHIP = AttributeDefinition(
    "ownership",
    "project.property_ownership",
    AttributeDataType.ENUM,
)
REGION = AttributeDefinition(
    "region",
    "project.location.region",
    AttributeDataType.GEO_ID,
)


def condition(
    identifier,
    attribute,
    operator,
    expected=None,
    **kwargs,
):
    return RuleCondition(
        identifier,
        attribute,
        operator,
        expected,
        **kwargs,
    )


def complete_verified(root):
    return RuleSet(
        "rs",
        root,
        CompletenessStatus.COMPLETE,
        VerificationStatus.VERIFIED,
    )


class Geography:
    def __init__(self, pairs):
        self.pairs = set(pairs)

    def is_within(self, actual_geography_id, expected_geography_id):
        return (
            actual_geography_id,
            expected_geography_id,
        ) in self.pairs


class EligibilityTruthTableTest(unittest.TestCase):
    def setUp(self):
        self.evaluator = EligibilityEvaluator()

    def test_and_truth_table(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "pop",
                    POPULATION,
                    ConditionOperator.LTE,
                    5000,
                ),
                condition(
                    "type",
                    APPLICANT_TYPE,
                    ConditionOperator.IN,
                    ["MUNICIPALITY", "SPORTS_CLUB"],
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(root),
            {
                POPULATION.key: 3200,
                APPLICANT_TYPE.key: "MUNICIPALITY",
            },
        )
        self.assertEqual(result.root_result, ConditionResult.PASS)
        self.assertEqual(result.status, EligibilityStatus.ELIGIBLE)

    def test_verified_blocking_fail_is_ineligible(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "pop",
                    POPULATION,
                    ConditionOperator.LTE,
                    5000,
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(root),
            {POPULATION.key: 8300},
        )
        self.assertEqual(result.status, EligibilityStatus.INELIGIBLE)

    def test_unverified_fail_needs_review_not_ineligible(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "pop",
                    POPULATION,
                    ConditionOperator.LTE,
                    5000,
                    verification_status=VerificationStatus.AUTO_EXTRACTED,
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(root),
            {POPULATION.key: 8300},
        )
        self.assertEqual(result.root_result, ConditionResult.FAIL)
        self.assertEqual(result.status, EligibilityStatus.NEEDS_REVIEW)

    def test_missing_value_needs_information(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "ownership",
                    OWNERSHIP,
                    ConditionOperator.EQ,
                    "OWNED",
                ),
            ),
        )
        result = self.evaluator.evaluate(complete_verified(root), {})
        self.assertEqual(result.root_result, ConditionResult.UNKNOWN)
        self.assertEqual(
            result.status,
            EligibilityStatus.NEEDS_INFORMATION,
        )

    def test_unknown_policy_not_applicable_does_not_fail(self):
        root = RuleGroup(
            "root",
            GroupOperator.OR,
            (
                condition(
                    "optional",
                    OWNERSHIP,
                    ConditionOperator.EQ,
                    "OWNED",
                    unknown_policy=UnknownPolicy.NOT_APPLICABLE,
                ),
                condition(
                    "type",
                    APPLICANT_TYPE,
                    ConditionOperator.EQ,
                    "SPORTS_CLUB",
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(root),
            {APPLICANT_TYPE.key: "SPORTS_CLUB"},
        )
        self.assertEqual(result.status, EligibilityStatus.ELIGIBLE)

    def test_nonblocking_fail_does_not_make_applicant_ineligible(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "type",
                    APPLICANT_TYPE,
                    ConditionOperator.EQ,
                    "SPORTS_CLUB",
                ),
                condition(
                    "advisory",
                    POPULATION,
                    ConditionOperator.LTE,
                    5000,
                    blocking=False,
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(root),
            {
                APPLICANT_TYPE.key: "SPORTS_CLUB",
                POPULATION.key: 10000,
            },
        )
        self.assertEqual(result.status, EligibilityStatus.ELIGIBLE)
        advisory = next(
            item for item in result.condition_results
            if item.condition_id == "advisory"
        )
        self.assertEqual(advisory.result, ConditionResult.FAIL)

    def test_incomplete_ruleset_can_only_be_likely_eligible(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "type",
                    APPLICANT_TYPE,
                    ConditionOperator.EQ,
                    "SPORTS_CLUB",
                ),
            ),
        )
        rule_set = RuleSet(
            "rs",
            root,
            CompletenessStatus.PARTIAL,
            VerificationStatus.VERIFIED,
        )
        result = self.evaluator.evaluate(
            rule_set,
            {APPLICANT_TYPE.key: "SPORTS_CLUB"},
        )
        self.assertEqual(
            result.status,
            EligibilityStatus.LIKELY_ELIGIBLE,
        )

    def test_type_mismatch_requires_review(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "pop",
                    POPULATION,
                    ConditionOperator.LTE,
                    5000,
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(root),
            {POPULATION.key: "3200"},
        )
        self.assertEqual(result.root_result, ConditionResult.ERROR)
        self.assertEqual(result.status, EligibilityStatus.NEEDS_REVIEW)

    def test_known_absent_supports_exists_and_not_exists(self):
        exists_root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "exists",
                    OWNERSHIP,
                    ConditionOperator.EXISTS,
                ),
            ),
        )
        result = self.evaluator.evaluate(
            complete_verified(exists_root),
            {OWNERSHIP.key: KNOWN_ABSENT},
        )
        self.assertEqual(result.status, EligibilityStatus.INELIGIBLE)


class GeographyTest(unittest.TestCase):
    def test_missing_geography_resolver_is_unknown(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "geo",
                    REGION,
                    ConditionOperator.GEO_WITHIN,
                    "CZ032",
                ),
            ),
        )
        result = EligibilityEvaluator().evaluate(
            complete_verified(root),
            {REGION.key: "CZ032"},
        )
        self.assertEqual(result.status, EligibilityStatus.NEEDS_INFORMATION)

    def test_geography_resolver_can_confirm_hierarchy(self):
        evaluator = EligibilityEvaluator(
            geography=Geography({("CZ0321", "CZ032")})
        )
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "geo",
                    REGION,
                    ConditionOperator.GEO_WITHIN,
                    "CZ032",
                ),
            ),
        )
        result = evaluator.evaluate(
            complete_verified(root),
            {REGION.key: "CZ0321"},
        )
        self.assertEqual(result.status, EligibilityStatus.ELIGIBLE)


class SnapshotTest(unittest.TestCase):
    def test_input_hash_is_order_independent(self):
        root = RuleGroup(
            "root",
            GroupOperator.AND,
            (
                condition(
                    "type",
                    APPLICANT_TYPE,
                    ConditionOperator.EQ,
                    "SPORTS_CLUB",
                ),
            ),
        )
        evaluator = EligibilityEvaluator()
        at = datetime(2026, 9, 23, tzinfo=timezone.utc)
        a = evaluator.evaluate(
            complete_verified(root),
            {"b": 2, "a": 1, APPLICANT_TYPE.key: "SPORTS_CLUB"},
            evaluated_at=at,
        )
        b = evaluator.evaluate(
            complete_verified(root),
            {APPLICANT_TYPE.key: "SPORTS_CLUB", "a": 1, "b": 2},
            evaluated_at=at,
        )
        self.assertEqual(a.input_snapshot_hash, b.input_snapshot_hash)


if __name__ == "__main__":
    unittest.main()
