import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "finance" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "eligibility" / "src"))

import dotacni_majak_eligibility
import dotacni_majak_finance
from dotacni_majak_eligibility import (
    AttributeDataType, AttributeDefinition, CompletenessStatus,
    ConditionOperator, EligibilityEvaluator, GroupOperator, RuleCondition,
    RuleGroup, RuleSet, VerificationStatus,
)
from dotacni_majak_finance import (
    ApplicantInput, FinanceEngine, FinanceStatus, FundingScenario, ScenarioApplicability,
    VersionedFundingScenario, select_from_eligibility,
)


class VerifiedFinanceSelectionTest(unittest.TestCase):
    def test_imports_are_from_current_worktree(self):
        assert dotacni_majak_eligibility.__file__ is not None
        assert dotacni_majak_finance.__file__ is not None
        self.assertEqual(
            Path(dotacni_majak_eligibility.__file__).resolve(),
            ROOT / "packages" / "eligibility" / "src" / "dotacni_majak_eligibility" / "__init__.py",
        )
        self.assertEqual(
            Path(dotacni_majak_finance.__file__).resolve(),
            ROOT / "packages" / "finance" / "src" / "dotacni_majak_finance" / "__init__.py",
        )

    def setUp(self):
        attribute = AttributeDefinition("type", "applicant.type", AttributeDataType.ENUM)
        self.root = RuleGroup("root", GroupOperator.OR, (
            RuleGroup("municipality", GroupOperator.AND, (
                RuleCondition("is-municipality", attribute, ConditionOperator.EQ, "MUNICIPALITY"),
            )),
            RuleGroup("club", GroupOperator.AND, (
                RuleCondition("is-club", attribute, ConditionOperator.EQ, "SPORTS_CLUB"),
            )),
        ))
        self.rule_set = RuleSet(
            "rule-set-1", self.root, CompletenessStatus.COMPLETE,
            VerificationStatus.VERIFIED,
        )
        self.scenarios = [
            VersionedFundingScenario(
                FundingScenario("municipality-rate", "CZK", condition_group_id="municipality"),
                "version-1",
            ),
            VersionedFundingScenario(
                FundingScenario("club-rate", "CZK", condition_group_id="club"),
                "version-1",
            ),
        ]
        self.evidence = {"is-municipality": "evidence:1", "is-club": "evidence:2"}

    def select(self, *, values=None, inputs=None, evidence=None, rule_set=None, scenarios=None,
               version="version-1", rules_version="version-1"):
        values = {"applicant.type": "MUNICIPALITY"} if values is None else values
        if inputs is None:
            inputs = {key: ApplicantInput(value, "ARES", "VERIFIED", f"input:{key}")
                      for key, value in values.items()}
        return select_from_eligibility(
            grant_call_version_id=version,
            rule_set_grant_call_version_id=rules_version,
            rule_set=self.rule_set if rule_set is None else rule_set,
            scenarios=self.scenarios if scenarios is None else scenarios,
            inputs=inputs,
            field_evidence_ids_by_condition=self.evidence if evidence is None else evidence,
            evaluator=EligibilityEvaluator(),
            finance_engine=FinanceEngine(),
        )

    def test_same_version_verified_evidenced_group_selects_one(self):
        result = self.select()
        self.assertEqual(result.status, FinanceStatus.COMPLETE)
        self.assertEqual(result.scenario.id, "municipality-rate")
        self.assertEqual(result.evidence_ids_by_group["municipality"], ("evidence:1",))
        self.assertEqual(result.evidence_ids_by_group["club"], ("evidence:2",))
        self.assertEqual(result.input_evidence_ids_by_group["municipality"], ("input:applicant.type",))
        self.assertEqual(result.rule_set_id, "rule-set-1")
        self.assertEqual(result.grant_call_version_id, "version-1")

    def test_input_provenance_must_be_verified_and_official_for_pass_and_fail(self):
        for source, verification, evidence_id in (
            ("USER", "USER_DECLARED", "input:1"),
            ("ARES", "NEEDS_REVIEW", "input:1"),
            ("ARES", "VERIFIED", None),
            ("CZSO", "VERIFIED", "  "),
            ("DERIVED", "VERIFIED", "input:1"),
        ):
            for value in ("MUNICIPALITY", "SPORTS_CLUB"):
                with self.subTest(source=source, verification=verification, value=value):
                    result = self.select(inputs={"applicant.type": ApplicantInput(
                        value, source, verification, evidence_id,
                    )})
                    self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
                    self.assertIsNone(result.scenario)
                    self.assertEqual(result.input_evidence_ids_by_group, {})
        self.assertEqual(self.select(inputs={}).status, FinanceStatus.NEEDS_INFORMATION)
        self.assertEqual(self.select(inputs={"applicant.type": "MUNICIPALITY"}).reason_codes,
                         ("INVALID_APPLICANT_INPUT",))

    def test_independent_condition_inputs_require_independent_evidence(self):
        attribute = AttributeDefinition("region", "project.region", AttributeDataType.ENUM)
        rule_set = RuleSet("rule-set-1", RuleGroup("root", GroupOperator.AND, (
            RuleGroup("municipality", GroupOperator.AND, (
                self.root.children[0].children[0],
                RuleCondition("region", attribute, ConditionOperator.EQ, "CZ010"),
            )),
            self.root.children[1],
        )), CompletenessStatus.COMPLETE, VerificationStatus.VERIFIED)
        first = ApplicantInput("MUNICIPALITY", "ARES", "VERIFIED", "input:type")
        second = ApplicantInput("CZ010", "CZSO", "VERIFIED", "input:region")
        evidence = {**self.evidence, "region": "evidence:region"}
        partial = self.select(rule_set=rule_set, evidence=evidence,
                              inputs={"applicant.type": first})
        self.assertEqual(partial.status, FinanceStatus.NEEDS_INFORMATION)
        complete = self.select(rule_set=rule_set, evidence=evidence,
                               inputs={"applicant.type": first, "project.region": second})
        self.assertEqual(complete.status, FinanceStatus.COMPLETE)
        self.assertEqual(complete.input_evidence_ids_by_group["municipality"],
                         ("input:type", "input:region"))

    def test_version_mismatch_fails_closed(self):
        for kwargs in (
            {"version": "version-2"},
            {"rules_version": "version-2"},
            {"version": ""},
        ):
            with self.subTest(kwargs=kwargs):
                result = self.select(**kwargs)
                self.assertEqual(result.status, FinanceStatus.ERROR)
                self.assertIsNone(result.scenario)
                self.assertEqual(result.reason_codes, ("GRANT_CALL_VERSION_MISMATCH",))
        other = [self.scenarios[0], VersionedFundingScenario(self.scenarios[1].scenario, "version-2")]
        self.assertEqual(self.select(scenarios=other).status, FinanceStatus.ERROR)

    def test_partial_or_unverified_rule_set_never_claims_pass(self):
        for completeness, verification in (
            (CompletenessStatus.PARTIAL, VerificationStatus.VERIFIED),
            (CompletenessStatus.COMPLETE, VerificationStatus.AUTO_EXTRACTED),
        ):
            rule_set = RuleSet("rule-set-1", self.root, completeness, verification)
            with self.subTest(completeness=completeness, verification=verification):
                result = self.select(rule_set=rule_set)
                self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
                self.assertIsNone(result.scenario)
                self.assertEqual(result.evidence_ids_by_group, {})

    def test_missing_unverified_or_blank_field_evidence_keeps_unknown(self):
        for evidence in ({"is-municipality": "evidence:1"},
                         {"is-municipality": "evidence:1", "is-club": "  "},
                         {}):
            with self.subTest(evidence=evidence):
                result = self.select(evidence=evidence)
                self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
                self.assertIsNone(result.scenario)

    def test_missing_profile_and_invalid_rule_cannot_select(self):
        missing = self.select(values={})
        self.assertEqual(missing.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(missing.scenario)
        bad = RuleSet("rule-set-1", RuleGroup("root", GroupOperator.AND, ()),
                      CompletenessStatus.COMPLETE, VerificationStatus.VERIFIED)
        invalid = self.select(rule_set=bad)
        self.assertEqual(invalid.status, FinanceStatus.ERROR)
        self.assertEqual(invalid.reason_codes, ("ELIGIBILITY_EVALUATION_ERROR",))

    def test_unverified_condition_or_unlinked_scenario_never_uses_legacy_pass(self):
        attribute = AttributeDefinition("type", "applicant.type", AttributeDataType.ENUM)
        unverified = RuleSet("rule-set-1", RuleGroup("root", GroupOperator.AND, (
            RuleGroup("municipality", GroupOperator.AND, (
                RuleCondition("is-municipality", attribute, ConditionOperator.EQ,
                              "MUNICIPALITY", verification_status=VerificationStatus.NEEDS_REVIEW),
            )),
        )), CompletenessStatus.COMPLETE, VerificationStatus.VERIFIED)
        result = self.select(rule_set=unverified, scenarios=[self.scenarios[0]])
        self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
        unlinked = VersionedFundingScenario(FundingScenario("unlinked", "CZK"), "version-1")
        result = self.select(scenarios=[unlinked])
        self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(result.scenario)

    def test_stored_fail_cannot_exclude_scenario_without_verified_group(self):
        stored_fail = VersionedFundingScenario(
            FundingScenario("club-rate", "CZK", condition_group_id="club",
                            applicability=ScenarioApplicability.FAIL),
            "version-1",
        )
        result = self.select(
            scenarios=[self.scenarios[0], stored_fail],
            evidence={"is-municipality": "evidence:1"},
        )
        self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(result.scenario)
        # Even a real group PASS cannot turn an unverified stored FAIL into
        # exclusion; an evidenced group FAIL can exclude the same scenario.
        passing = self.select(
            scenarios=[self.scenarios[0], stored_fail],
            values={"applicant.type": "SPORTS_CLUB"},
        )
        self.assertEqual(passing.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(passing.scenario)
        failed_group = self.select(scenarios=[self.scenarios[0], stored_fail])
        self.assertEqual(failed_group.status, FinanceStatus.COMPLETE)
        self.assertEqual(failed_group.scenario.id, "municipality-rate")

    def test_masked_condition_error_blocks_even_if_root_passes(self):
        number = AttributeDefinition("age", "project.age", AttributeDataType.INTEGER)
        malformed = RuleSet("rule-set-1", RuleGroup("root", GroupOperator.OR, (
            self.root.children[0],
            RuleCondition("bad-range", number, ConditionOperator.BETWEEN, [10, 1]),
        )), CompletenessStatus.COMPLETE, VerificationStatus.VERIFIED)
        result = self.select(
            rule_set=malformed,
            scenarios=[self.scenarios[0]],
            values={"applicant.type": "MUNICIPALITY", "project.age": 5},
            evidence={"is-municipality": "evidence:1", "bad-range": "evidence:3"},
        )
        self.assertEqual(result.status, FinanceStatus.ERROR)
        self.assertEqual(result.reason_codes, ("ELIGIBILITY_EVALUATION_ERROR",))
        self.assertIsNone(result.scenario)

    def test_duplicate_scenarios_and_unknown_group_never_select(self):
        duplicate = [self.scenarios[0], self.scenarios[0]]
        result = self.select(scenarios=duplicate)
        self.assertEqual(result.status, FinanceStatus.ERROR)
        self.assertEqual(result.reason_codes, ("DUPLICATE_SCENARIO_ID",))
        missing = VersionedFundingScenario(
            FundingScenario("unmapped", "CZK", condition_group_id="not-in-rule-tree"),
            "version-1",
        )
        result = self.select(scenarios=[self.scenarios[0], missing])
        self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(result.scenario)

    def test_duplicate_condition_ids_and_group_ids_fail_closed(self):
        attribute = AttributeDefinition("type", "applicant.type", AttributeDataType.ENUM)
        duplicate = RuleSet("rule-set-1", RuleGroup("root", GroupOperator.OR, (
            RuleGroup("a", GroupOperator.AND, (
                RuleCondition("same", attribute, ConditionOperator.EQ, "MUNICIPALITY"),
            )),
            RuleGroup("b", GroupOperator.AND, (
                RuleCondition("same", attribute, ConditionOperator.EQ, "SPORTS_CLUB"),
            )),
        )), CompletenessStatus.COMPLETE, VerificationStatus.VERIFIED)
        self.assertEqual(self.select(rule_set=duplicate).reason_codes,
                         ("DUPLICATE_CONDITION_ID",))
        duplicated_groups = RuleSet("rule-set-1", RuleGroup("root", GroupOperator.OR, (
            self.root.children[0], self.root.children[0],
        )), CompletenessStatus.COMPLETE, VerificationStatus.VERIFIED)
        self.assertEqual(self.select(rule_set=duplicated_groups).status, FinanceStatus.ERROR)


if __name__ == "__main__":
    unittest.main()
