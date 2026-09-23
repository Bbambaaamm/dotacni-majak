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
