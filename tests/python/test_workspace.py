import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for relative in (
    ("packages", "workspace", "src"),
    ("packages", "eligibility", "src"),
    ("packages", "finance", "src"),
):
    sys.path.insert(0, str(ROOT.joinpath(*relative)))

from dotacni_majak_eligibility import (
    ConditionEvaluation,
    ConditionResult,
    EligibilityEvaluation,
    EligibilityStatus,
    VerificationStatus,
)
from dotacni_majak_finance import FinanceEvaluation, FinanceStatus
from dotacni_majak_workspace import (
    GrantRequirementInput,
    ReadinessState,
    RequirementNecessity,
    WorkspaceEngine,
    WorkspaceStatus,
    WorkspaceTaskSource,
    WorkspaceTaskStatus,
)


AT = datetime(2026, 9, 23, tzinfo=timezone.utc)


def eligibility(status, *, unknown=False):
    conditions = ()
    if unknown:
        conditions = (
            ConditionEvaluation(
                condition_id="ownership",
                attribute_key="project.property_ownership",
                result=ConditionResult.UNKNOWN,
                blocking=True,
                verification_status=VerificationStatus.VERIFIED,
                actual_value=None,
                expected_value=["OWNED", "LONG_LEASE"],
                reason_code="MISSING_INPUT",
            ),
        )
    return EligibilityEvaluation(
        rule_set_id="rs1",
        status=status,
        root_result=(
            ConditionResult.UNKNOWN
            if status is EligibilityStatus.NEEDS_INFORMATION
            else (
                ConditionResult.FAIL
                if status is EligibilityStatus.INELIGIBLE
                else ConditionResult.PASS
            )
        ),
        condition_results=conditions,
        input_snapshot_hash="a" * 64,
        evaluated_at=AT,
    )


def finance(status, reasons=()):
    return FinanceEvaluation(
        status=status,
        scenario_id="s1",
        currency_code="CZK",
        max_grant_minor=None,
        own_eligible_contribution_minor=None,
        ineligible_costs_minor=None,
        nonrecoverable_vat_minor=None,
        minimum_real_cash_requirement_minor=None,
        minimum_prefinancing_requirement_minor=None,
        reason_codes=tuple(reasons),
    )


class WorkspaceEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = WorkspaceEngine()

    def test_unknown_eligibility_and_finance_create_blocking_next_actions(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(
                GrantRequirementInput(
                    id="budget",
                    title="Položkový rozpočet",
                    necessity=RequirementNecessity.REQUIRED,
                ),
            ),
            eligibility=eligibility(
                EligibilityStatus.NEEDS_INFORMATION,
                unknown=True,
            ),
            finance=finance(
                FinanceStatus.NEEDS_INFORMATION,
                ("MISSING_NONRECOVERABLE_VAT",),
            ),
        )

        readiness = self.engine.readiness(workspace)
        self.assertEqual(readiness.state, ReadinessState.NEEDS_ACTION)
        self.assertGreaterEqual(readiness.blocking_open_count, 3)
        self.assertEqual(
            readiness.next_action.source,
            WorkspaceTaskSource.ELIGIBILITY,
        )
        self.assertEqual(workspace.status, WorkspaceStatus.PREPARING)

    def test_recommended_task_does_not_block_ready(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(
                GrantRequirementInput(
                    id="recommended",
                    title="Doporučený podklad",
                    necessity=RequirementNecessity.RECOMMENDED,
                ),
            ),
            eligibility=eligibility(EligibilityStatus.ELIGIBLE),
            finance=finance(FinanceStatus.COMPLETE),
        )
        readiness = self.engine.readiness(workspace)
        self.assertEqual(readiness.state, ReadinessState.READY)
        self.assertEqual(workspace.status, WorkspaceStatus.READY_TO_SUBMIT)
        self.assertEqual(readiness.completion_percent, 0)

    def test_conditional_false_is_not_applicable(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(
                GrantRequirementInput(
                    id="permit",
                    title="Stavební povolení",
                    necessity=RequirementNecessity.CONDITIONAL,
                    condition_applies=False,
                ),
            ),
            eligibility=eligibility(EligibilityStatus.ELIGIBLE),
            finance=finance(FinanceStatus.COMPLETE),
        )
        task = workspace.tasks[0]
        self.assertEqual(task.status, WorkspaceTaskStatus.NOT_APPLICABLE)
        self.assertEqual(
            self.engine.readiness(workspace).state,
            ReadinessState.READY,
        )

    def test_required_tasks_can_be_completed_to_ready(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(
                GrantRequirementInput(
                    id="budget",
                    title="Rozpočet",
                    necessity=RequirementNecessity.REQUIRED,
                ),
                GrantRequirementInput(
                    id="ownership",
                    title="Doklad o vlastnictví",
                    necessity=RequirementNecessity.REQUIRED,
                ),
            ),
            eligibility=eligibility(EligibilityStatus.ELIGIBLE),
            finance=finance(FinanceStatus.COMPLETE),
        )
        for task in workspace.tasks:
            if task.blocking:
                workspace = self.engine.update_task_status(
                    workspace,
                    task_id=task.id,
                    status=WorkspaceTaskStatus.DONE,
                )

        readiness = self.engine.readiness(workspace)
        self.assertEqual(readiness.state, ReadinessState.READY)
        self.assertEqual(readiness.completion_percent, 100)
        self.assertEqual(workspace.status, WorkspaceStatus.READY_TO_SUBMIT)

    def test_ineligible_is_explicitly_blocked(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(),
            eligibility=eligibility(EligibilityStatus.INELIGIBLE),
            finance=finance(FinanceStatus.COMPLETE),
        )
        readiness = self.engine.readiness(workspace)
        self.assertEqual(readiness.state, ReadinessState.BLOCKED)
        self.assertEqual(
            readiness.next_action.reason_code,
            "ELIGIBILITY_INELIGIBLE",
        )

    def test_unsupported_finance_instrument_creates_explicit_blocker(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(),
            eligibility=eligibility(EligibilityStatus.ELIGIBLE),
            finance=finance(FinanceStatus.INSTRUMENT_NOT_SUPPORTED),
        )
        readiness = self.engine.readiness(workspace)
        self.assertEqual(readiness.state, ReadinessState.BLOCKED)
        self.assertEqual(
            readiness.next_action.reason_code,
            "FINANCE_INSTRUMENT_NOT_SUPPORTED",
        )
        self.assertIn("specializovaný finanční výpočet", readiness.next_action.title)

    def test_baseline_version_change_requires_review(self):
        workspace = self.engine.create(
            workspace_id="w1",
            project_id="p1",
            grant_call_id="g1",
            baseline_grant_version_id="v1",
            requirements=(),
            eligibility=eligibility(EligibilityStatus.ELIGIBLE),
            finance=finance(FinanceStatus.COMPLETE),
        )
        self.assertFalse(workspace.needs_version_review("v1"))
        self.assertTrue(workspace.needs_version_review("v2"))


if __name__ == "__main__":
    unittest.main()
