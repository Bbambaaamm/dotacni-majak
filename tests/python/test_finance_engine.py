import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "finance" / "src"))

from dotacni_majak_finance import (
    FinanceEngine,
    FinanceStatus,
    FundingInstrumentType,
    FundingScenario,
    PaymentMode,
    ProjectFinanceInput,
    ScenarioApplicability,
)


def czk(value: int) -> int:
    return value * 100


class FinanceEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = FinanceEngine()

    def test_tennis_example_calculates_real_cash_requirement(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(3_500_000),
            ineligible_costs_minor=czk(400_000),
            nonrecoverable_vat_minor=czk(100_000),
        )
        scenario = FundingScenario(
            id="sports-90",
            currency_code="CZK",
            support_rate_max_bps=9000,
        )

        result = self.engine.evaluate(project, scenario)

        self.assertEqual(result.status, FinanceStatus.COMPLETE)
        self.assertEqual(result.max_grant_minor, czk(3_150_000))
        self.assertEqual(
            result.own_eligible_contribution_minor,
            czk(350_000),
        )
        self.assertEqual(
            result.minimum_real_cash_requirement_minor,
            czk(850_000),
        )

    def test_grant_cap_increases_own_cash_requirement(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(4_000_000),
            ineligible_costs_minor=0,
            nonrecoverable_vat_minor=0,
        )
        scenario = FundingScenario(
            id="capped",
            currency_code="CZK",
            support_rate_max_bps=9000,
            grant_amount_max_minor=czk(2_000_000),
        )

        result = self.engine.evaluate(project, scenario)
        self.assertEqual(result.max_grant_minor, czk(2_000_000))
        self.assertEqual(
            result.minimum_real_cash_requirement_minor,
            czk(2_000_000),
        )

    def test_missing_vat_does_not_silently_become_zero(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(3_500_000),
            ineligible_costs_minor=czk(500_000),
            nonrecoverable_vat_minor=None,
        )
        scenario = FundingScenario(
            id="s",
            currency_code="CZK",
            support_rate_max_bps=9000,
        )

        result = self.engine.evaluate(project, scenario)
        self.assertEqual(result.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIn("MISSING_NONRECOVERABLE_VAT", result.reason_codes)
        self.assertIsNone(result.minimum_real_cash_requirement_minor)

    def test_project_cost_outside_scenario_is_not_applicable(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(2_000_000),
            eligible_costs_minor=czk(2_000_000),
            ineligible_costs_minor=0,
            nonrecoverable_vat_minor=0,
        )
        scenario = FundingScenario(
            id="min-3m",
            currency_code="CZK",
            support_rate_max_bps=8000,
            project_cost_min_minor=czk(3_000_000),
        )

        result = self.engine.evaluate(project, scenario)
        self.assertEqual(
            result.status,
            FinanceStatus.SCENARIO_NOT_APPLICABLE,
        )
        self.assertIn("PROJECT_COST_BELOW_MINIMUM", result.reason_codes)

    def test_reimbursement_without_advance_exposes_prefinancing(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(3_500_000),
            ineligible_costs_minor=czk(500_000),
            nonrecoverable_vat_minor=0,
        )
        scenario = FundingScenario(
            id="refund",
            currency_code="CZK",
            support_rate_max_bps=9000,
            payment_mode=PaymentMode.REIMBURSEMENT,
            advance_payment_allowed=False,
        )

        result = self.engine.evaluate(project, scenario)
        self.assertEqual(
            result.minimum_prefinancing_requirement_minor,
            czk(4_000_000),
        )

    def test_multiple_applicable_scenarios_are_not_auto_ranked(self):
        status, selected, reasons = self.engine.select_scenario(
            [
                FundingScenario(
                    id="municipality-a",
                    currency_code="CZK",
                    applicability=ScenarioApplicability.PASS,
                    support_rate_max_bps=9000,
                ),
                FundingScenario(
                    id="municipality-b",
                    currency_code="CZK",
                    applicability=ScenarioApplicability.PASS,
                    support_rate_max_bps=8000,
                ),
            ]
        )
        self.assertEqual(status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(selected)
        self.assertIn("MULTIPLE_APPLICABLE_SCENARIOS", reasons)

    def test_unknown_scenario_applicability_stays_unknown(self):
        status, selected, reasons = self.engine.select_scenario(
            [
                FundingScenario(
                    id="conditional",
                    currency_code="CZK",
                    applicability=ScenarioApplicability.UNKNOWN,
                )
            ]
        )
        self.assertEqual(status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(selected)
        self.assertIn("SCENARIO_APPLICABILITY_UNKNOWN", reasons)

    def test_pass_and_unknown_never_claim_unique_scenario(self):
        known = FundingScenario(id="known", currency_code="CZK")
        possible = FundingScenario(
            id="possible", currency_code="CZK",
            applicability=ScenarioApplicability.UNKNOWN,
        )
        for scenarios in ([known, possible], [possible, known]):
            with self.subTest(order=[s.id for s in scenarios]):
                status, selected, reasons = self.engine.select_scenario(scenarios)
                self.assertEqual(status, FinanceStatus.NEEDS_INFORMATION)
                self.assertIsNone(selected)
                self.assertEqual(reasons, ("SCENARIO_APPLICABILITY_UNKNOWN",))

    def test_condition_group_results_select_only_unambiguous_pass(self):
        local = FundingScenario(
            id="local", currency_code="CZK", condition_group_id="municipality",
        )
        nonprofit = FundingScenario(
            id="nonprofit", currency_code="CZK", condition_group_id="nonprofit",
        )
        status, selected, reasons = self.engine.select_scenario(
            [local, nonprofit],
            group_results={
                "municipality": ScenarioApplicability.PASS,
                "nonprofit": ScenarioApplicability.FAIL,
            },
        )
        self.assertEqual((status, selected, reasons), (FinanceStatus.COMPLETE, local, ()))
        for results, expected in (
            ({"municipality": ScenarioApplicability.PASS}, "SCENARIO_CONDITION_GROUP_RESULT_MISSING"),
            ({"municipality": ScenarioApplicability.PASS, "nonprofit": ScenarioApplicability.UNKNOWN}, "SCENARIO_APPLICABILITY_UNKNOWN"),
        ):
            with self.subTest(results=results):
                status, selected, reasons = self.engine.select_scenario(
                    [local, nonprofit], group_results=results,
                )
                self.assertEqual((status, selected, reasons), (FinanceStatus.NEEDS_INFORMATION, None, (expected,)))

    def test_all_failed_group_results_are_not_applicable(self):
        linked = FundingScenario(id="linked", currency_code="CZK", condition_group_id="group")
        self.assertEqual(
            self.engine.select_scenario(
                [linked], group_results={"group": ScenarioApplicability.FAIL},
            ),
            (FinanceStatus.SCENARIO_NOT_APPLICABLE, None, ("NO_APPLICABLE_SCENARIO",)),
        )

    def test_unresolved_group_cannot_be_evaluated_directly(self):
        project = ProjectFinanceInput("CZK", czk(100), czk(100), 0, 0)
        linked = FundingScenario(
            id="linked", currency_code="CZK", condition_group_id="group",
            support_rate_max_bps=5000,
        )
        missing = self.engine.evaluate(project, linked)
        self.assertEqual(missing.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(missing.max_grant_minor)
        unknown = self.engine.evaluate(
            project, linked, group_result=ScenarioApplicability.UNKNOWN,
        )
        self.assertEqual(unknown.status, FinanceStatus.NEEDS_INFORMATION)
        self.assertIsNone(unknown.max_grant_minor)
        failed = self.engine.evaluate(project, linked, group_result=ScenarioApplicability.FAIL)
        self.assertEqual(failed.status, FinanceStatus.SCENARIO_NOT_APPLICABLE)
        self.assertIsNone(failed.minimum_real_cash_requirement_minor)
        passed = self.engine.evaluate(project, linked, group_result=ScenarioApplicability.PASS)
        self.assertEqual(passed.status, FinanceStatus.COMPLETE)
        self.assertEqual(passed.max_grant_minor, czk(50))

    def test_duplicate_ids_and_invalid_group_results_fail_closed(self):
        linked = FundingScenario(id="same", currency_code="CZK", condition_group_id="group")
        self.assertEqual(
            self.engine.select_scenario([linked, linked]),
            (FinanceStatus.ERROR, None, ("DUPLICATE_SCENARIO_ID",)),
        )
        self.assertEqual(
            self.engine.select_scenario([linked], group_results={"group": "PASS"}),
            (FinanceStatus.ERROR, None, ("INVALID_CONDITION_GROUP_RESULT",)),
        )

    def test_non_grant_instrument_never_uses_grant_calculator(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(10_000_000),
            eligible_costs_minor=czk(10_000_000),
            ineligible_costs_minor=0,
            nonrecoverable_vat_minor=0,
        )
        scenario = FundingScenario(
            id="nrb-guarantee",
            currency_code="CZK",
            instrument_type=FundingInstrumentType.GUARANTEE,
            support_rate_max_bps=7000,
        )

        result = self.engine.evaluate(project, scenario)

        self.assertEqual(
            result.status,
            FinanceStatus.INSTRUMENT_NOT_SUPPORTED,
        )
        self.assertEqual(
            result.instrument_type,
            FundingInstrumentType.GUARANTEE,
        )
        self.assertIn(
            "INSTRUMENT_GUARANTEE_REQUIRES_SPECIALIZED_ENGINE",
            result.reason_codes,
        )
        self.assertIsNone(result.max_grant_minor)
        self.assertIsNone(result.minimum_real_cash_requirement_minor)

    def test_component_sum_mismatch_is_error(self):
        project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(3_500_000),
            ineligible_costs_minor=czk(600_000),
            nonrecoverable_vat_minor=0,
        )
        scenario = FundingScenario(
            id="s",
            currency_code="CZK",
            support_rate_max_bps=9000,
        )
        result = self.engine.evaluate(project, scenario)
        self.assertEqual(result.status, FinanceStatus.ERROR)
        self.assertIn(
            "PROJECT_COST_COMPONENTS_DO_NOT_SUM_TO_TOTAL",
            result.reason_codes,
        )


if __name__ == "__main__":
    unittest.main()
