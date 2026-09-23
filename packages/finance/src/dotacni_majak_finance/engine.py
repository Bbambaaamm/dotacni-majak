from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FinanceStatus(str, Enum):
    COMPLETE = "COMPLETE"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    SCENARIO_NOT_APPLICABLE = "SCENARIO_NOT_APPLICABLE"
    INSTRUMENT_NOT_SUPPORTED = "INSTRUMENT_NOT_SUPPORTED"
    ERROR = "ERROR"


class FundingInstrumentType(str, Enum):
    GRANT = "GRANT"
    LOAN = "LOAN"
    GUARANTEE = "GUARANTEE"
    EQUITY = "EQUITY"
    MIXED = "MIXED"
    OTHER = "OTHER"


class ScenarioApplicability(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class PaymentMode(str, Enum):
    ADVANCE = "ADVANCE"
    REIMBURSEMENT = "REIMBURSEMENT"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FundingScenario:
    id: str
    currency_code: str
    instrument_type: FundingInstrumentType = FundingInstrumentType.GRANT
    applicability: ScenarioApplicability = ScenarioApplicability.PASS
    support_rate_min_bps: int | None = None
    support_rate_max_bps: int | None = None
    grant_amount_min_minor: int | None = None
    grant_amount_max_minor: int | None = None
    project_cost_min_minor: int | None = None
    project_cost_max_minor: int | None = None
    payment_mode: PaymentMode = PaymentMode.UNKNOWN
    advance_payment_allowed: bool | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("scenario id must not be empty")
        if len(self.currency_code) != 3 or not self.currency_code.isupper():
            raise ValueError("currency_code must be ISO-like uppercase code")
        for name, value in (
            ("support_rate_min_bps", self.support_rate_min_bps),
            ("support_rate_max_bps", self.support_rate_max_bps),
        ):
            if value is not None and not 0 <= value <= 10_000:
                raise ValueError(f"{name} must be between 0 and 10000")
        for name, value in (
            ("grant_amount_min_minor", self.grant_amount_min_minor),
            ("grant_amount_max_minor", self.grant_amount_max_minor),
            ("project_cost_min_minor", self.project_cost_min_minor),
            ("project_cost_max_minor", self.project_cost_max_minor),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must be >= 0")
        if (
            self.support_rate_min_bps is not None
            and self.support_rate_max_bps is not None
            and self.support_rate_min_bps > self.support_rate_max_bps
        ):
            raise ValueError("support rate min exceeds max")
        if (
            self.grant_amount_min_minor is not None
            and self.grant_amount_max_minor is not None
            and self.grant_amount_min_minor > self.grant_amount_max_minor
        ):
            raise ValueError("grant amount min exceeds max")
        if (
            self.project_cost_min_minor is not None
            and self.project_cost_max_minor is not None
            and self.project_cost_min_minor > self.project_cost_max_minor
        ):
            raise ValueError("project cost min exceeds max")


@dataclass(frozen=True, slots=True)
class ProjectFinanceInput:
    currency_code: str
    total_project_cost_minor: int | None
    eligible_costs_minor: int | None
    ineligible_costs_minor: int | None
    nonrecoverable_vat_minor: int | None

    def __post_init__(self) -> None:
        for name, value in (
            ("total_project_cost_minor", self.total_project_cost_minor),
            ("eligible_costs_minor", self.eligible_costs_minor),
            ("ineligible_costs_minor", self.ineligible_costs_minor),
            ("nonrecoverable_vat_minor", self.nonrecoverable_vat_minor),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must be >= 0")


@dataclass(frozen=True, slots=True)
class FinanceEvaluation:
    status: FinanceStatus
    scenario_id: str | None
    currency_code: str
    max_grant_minor: int | None
    own_eligible_contribution_minor: int | None
    ineligible_costs_minor: int | None
    nonrecoverable_vat_minor: int | None
    minimum_real_cash_requirement_minor: int | None
    minimum_prefinancing_requirement_minor: int | None
    reason_codes: tuple[str, ...]
    instrument_type: FundingInstrumentType = FundingInstrumentType.GRANT
    engine_version: str = "finance-v1"


class FinanceEngine:
    """Deterministic grant-finance calculator using integer minor units/bps.

    The engine calculates the *maximum supported grant under known rules* and
    therefore the corresponding *minimum known own cash requirement*. It never
    turns missing cost/VAT/rule data into zero.
    """

    def __init__(self, *, engine_version: str = "finance-v1") -> None:
        self.engine_version = engine_version

    def select_scenario(
        self,
        scenarios: list[FundingScenario] | tuple[FundingScenario, ...],
    ) -> tuple[FinanceStatus, FundingScenario | None, tuple[str, ...]]:
        passed = [
            scenario
            for scenario in scenarios
            if scenario.applicability is ScenarioApplicability.PASS
        ]
        unknown = [
            scenario
            for scenario in scenarios
            if scenario.applicability is ScenarioApplicability.UNKNOWN
        ]

        if len(passed) == 1:
            return FinanceStatus.COMPLETE, passed[0], ()

        if len(passed) > 1:
            return (
                FinanceStatus.NEEDS_INFORMATION,
                None,
                ("MULTIPLE_APPLICABLE_SCENARIOS",),
            )

        if unknown:
            return (
                FinanceStatus.NEEDS_INFORMATION,
                None,
                ("SCENARIO_APPLICABILITY_UNKNOWN",),
            )

        return (
            FinanceStatus.SCENARIO_NOT_APPLICABLE,
            None,
            ("NO_APPLICABLE_SCENARIO",),
        )

    def evaluate(
        self,
        project: ProjectFinanceInput,
        scenario: FundingScenario,
    ) -> FinanceEvaluation:
        reasons: list[str] = []

        if scenario.instrument_type is not FundingInstrumentType.GRANT:
            return self._result(
                FinanceStatus.INSTRUMENT_NOT_SUPPORTED,
                scenario,
                project,
                reasons=(
                    f"INSTRUMENT_{scenario.instrument_type.value}_REQUIRES_SPECIALIZED_ENGINE",
                ),
            )

        if project.currency_code != scenario.currency_code:
            return self._result(
                FinanceStatus.ERROR,
                scenario,
                project,
                reasons=("CURRENCY_MISMATCH",),
            )

        if scenario.applicability is ScenarioApplicability.FAIL:
            return self._result(
                FinanceStatus.SCENARIO_NOT_APPLICABLE,
                scenario,
                project,
                reasons=("SCENARIO_CONDITIONS_FAIL",),
            )
        if scenario.applicability is ScenarioApplicability.UNKNOWN:
            return self._result(
                FinanceStatus.NEEDS_INFORMATION,
                scenario,
                project,
                reasons=("SCENARIO_APPLICABILITY_UNKNOWN",),
            )

        missing = [
            name
            for name, value in (
                ("ELIGIBLE_COSTS", project.eligible_costs_minor),
                ("INELIGIBLE_COSTS", project.ineligible_costs_minor),
                ("NONRECOVERABLE_VAT", project.nonrecoverable_vat_minor),
                ("TOTAL_PROJECT_COST", project.total_project_cost_minor),
            )
            if value is None
        ]
        if scenario.support_rate_max_bps is None:
            missing.append("SUPPORT_RATE_MAX")

        if missing:
            return self._result(
                FinanceStatus.NEEDS_INFORMATION,
                scenario,
                project,
                reasons=tuple(f"MISSING_{name}" for name in missing),
            )

        assert project.total_project_cost_minor is not None
        assert project.eligible_costs_minor is not None
        assert project.ineligible_costs_minor is not None
        assert project.nonrecoverable_vat_minor is not None
        assert scenario.support_rate_max_bps is not None

        components_total = (
            project.eligible_costs_minor
            + project.ineligible_costs_minor
            + project.nonrecoverable_vat_minor
        )
        if components_total != project.total_project_cost_minor:
            return self._result(
                FinanceStatus.ERROR,
                scenario,
                project,
                reasons=("PROJECT_COST_COMPONENTS_DO_NOT_SUM_TO_TOTAL",),
            )

        if (
            scenario.project_cost_min_minor is not None
            and project.total_project_cost_minor < scenario.project_cost_min_minor
        ):
            return self._result(
                FinanceStatus.SCENARIO_NOT_APPLICABLE,
                scenario,
                project,
                reasons=("PROJECT_COST_BELOW_MINIMUM",),
            )

        if (
            scenario.project_cost_max_minor is not None
            and project.total_project_cost_minor > scenario.project_cost_max_minor
        ):
            return self._result(
                FinanceStatus.SCENARIO_NOT_APPLICABLE,
                scenario,
                project,
                reasons=("PROJECT_COST_ABOVE_MAXIMUM",),
            )

        # Floor is conservative for a maximum-grant estimate: it never claims
        # more public support than integer minor units can justify.
        grant = (
            project.eligible_costs_minor
            * scenario.support_rate_max_bps
            // 10_000
        )
        if scenario.grant_amount_max_minor is not None:
            grant = min(grant, scenario.grant_amount_max_minor)

        if (
            scenario.grant_amount_min_minor is not None
            and grant < scenario.grant_amount_min_minor
        ):
            return self._result(
                FinanceStatus.SCENARIO_NOT_APPLICABLE,
                scenario,
                project,
                reasons=("CALCULATED_GRANT_BELOW_MINIMUM",),
            )

        own_eligible = project.eligible_costs_minor - grant
        minimum_cash = (
            own_eligible
            + project.ineligible_costs_minor
            + project.nonrecoverable_vat_minor
        )

        prefinancing: int | None = None
        if (
            scenario.payment_mode is PaymentMode.REIMBURSEMENT
            and scenario.advance_payment_allowed is False
        ):
            prefinancing = project.total_project_cost_minor
        elif scenario.payment_mode is PaymentMode.UNKNOWN:
            reasons.append("PREFINANCING_RULE_UNKNOWN")

        return FinanceEvaluation(
            status=FinanceStatus.COMPLETE,
            scenario_id=scenario.id,
            currency_code=project.currency_code,
            instrument_type=scenario.instrument_type,
            max_grant_minor=grant,
            own_eligible_contribution_minor=own_eligible,
            ineligible_costs_minor=project.ineligible_costs_minor,
            nonrecoverable_vat_minor=project.nonrecoverable_vat_minor,
            minimum_real_cash_requirement_minor=minimum_cash,
            minimum_prefinancing_requirement_minor=prefinancing,
            reason_codes=tuple(reasons),
            engine_version=self.engine_version,
        )

    def _result(
        self,
        status: FinanceStatus,
        scenario: FundingScenario,
        project: ProjectFinanceInput,
        *,
        reasons: tuple[str, ...],
    ) -> FinanceEvaluation:
        return FinanceEvaluation(
            status=status,
            scenario_id=scenario.id,
            currency_code=project.currency_code,
            instrument_type=scenario.instrument_type,
            max_grant_minor=None,
            own_eligible_contribution_minor=None,
            ineligible_costs_minor=project.ineligible_costs_minor,
            nonrecoverable_vat_minor=project.nonrecoverable_vat_minor,
            minimum_real_cash_requirement_minor=None,
            minimum_prefinancing_requirement_minor=None,
            reason_codes=reasons,
            engine_version=self.engine_version,
        )
