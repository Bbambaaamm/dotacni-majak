import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for rel in (
    ("packages", "checklist", "src"),
    ("packages", "workspace", "src"),
    ("packages", "eligibility", "src"),
):
    sys.path.insert(0, str(ROOT.joinpath(*rel)))

import unittest
from dotacni_majak_checklist import (
    Checklist,
    ChecklistDiff,
    ChecklistItem,
    ChecklistItemStatus,
    RequirementChecklistGenerator,
)
from dotacni_majak_eligibility import (
    ConditionEvaluation,
    ConditionResult,
    EligibilityEvaluation,
    EligibilityStatus,
    VerificationStatus,
)
from dotacni_majak_workspace import (
    GrantRequirementInput,
    RequirementNecessity,
)


AT = datetime(2026, 9, 23, tzinfo=timezone.utc)
GEN = RequirementChecklistGenerator()


def req(id, title, necessity, *, condition_applies=None, due_at=None):
    return GrantRequirementInput(
        id=id, title=title, necessity=necessity,
        condition_applies=condition_applies, due_at=due_at,
    )


def eligible():
    return EligibilityEvaluation(
        rule_set_id="rs1",
        status=EligibilityStatus.ELIGIBLE,
        root_result=ConditionResult.PASS,
        condition_results=(),
        input_snapshot_hash="a" * 64,
        evaluated_at=AT,
    )


def ineligible():
    return EligibilityEvaluation(
        rule_set_id="rs1",
        status=EligibilityStatus.INELIGIBLE,
        root_result=ConditionResult.FAIL,
        condition_results=(),
        input_snapshot_hash="a" * 64,
        evaluated_at=AT,
    )


def needs_review():
    return EligibilityEvaluation(
        rule_set_id="rs1",
        status=EligibilityStatus.NEEDS_REVIEW,
        root_result=ConditionResult.UNKNOWN,
        condition_results=(),
        input_snapshot_hash="a" * 64,
        evaluated_at=AT,
    )


def needs_info(unknown_condition=None):
    conditions = ()
    if unknown_condition:
        conditions = (unknown_condition,)
    return EligibilityEvaluation(
        rule_set_id="rs1",
        status=EligibilityStatus.NEEDS_INFORMATION,
        root_result=ConditionResult.UNKNOWN,
        condition_results=conditions,
        input_snapshot_hash="a" * 64,
        evaluated_at=AT,
    )


class RequirementChecklistGeneratorTest(unittest.TestCase):
    def test_required_generates_todo_blocking(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Položkový rozpočet", RequirementNecessity.REQUIRED)],
            eligibility=eligible(),
        ).items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].necessity, "REQUIRED")
        self.assertEqual(items[0].status, ChecklistItemStatus.TODO)
        self.assertTrue(items[0].blocking)
        self.assertEqual(items[0].priority, 30)
        self.assertEqual(items[0].source, "REQUIREMENT")
        self.assertEqual(items[0].reference_id, "r1")

    def test_conditional_false_is_not_applicable(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Stavební povolení", RequirementNecessity.CONDITIONAL,
                               condition_applies=False)],
            eligibility=eligible(),
        ).items
        self.assertEqual(items[0].status, ChecklistItemStatus.NOT_APPLICABLE)
        self.assertFalse(items[0].blocking)
        self.assertEqual(items[0].priority, 100)

    def test_conditional_true_is_blocking_todo(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Dočasné zázemí", RequirementNecessity.CONDITIONAL,
                               condition_applies=True)],
            eligibility=eligible(),
        ).items
        self.assertEqual(items[0].status, ChecklistItemStatus.TODO)
        self.assertTrue(items[0].blocking)
        self.assertEqual(items[0].priority, 30)

    def test_conditional_unknown_is_blocking_todo(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Působiště", RequirementNecessity.CONDITIONAL,
                               condition_applies=None)],
            eligibility=eligible(),
        ).items
        self.assertEqual(items[0].status, ChecklistItemStatus.TODO)
        self.assertTrue(items[0].blocking)

    def test_recommended_is_non_blocking_todo(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Doporučený příloha", RequirementNecessity.RECOMMENDED)],
            eligibility=eligible(),
        ).items
        self.assertEqual(items[0].status, ChecklistItemStatus.TODO)
        self.assertFalse(items[0].blocking)
        self.assertEqual(items[0].priority, 100)

    def test_evidence_id_planned_for_schema(self):
        """GrantRequirement schema defines evidenceId; generator reserves field
        for when GrantRequirementInput grows the field."""
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Rozpočet", RequirementNecessity.REQUIRED)],
            eligibility=eligible(),
        ).items
        self.assertIsNone(items[0].evidence_id)  # not wired yet

    def test_due_at_is_preserved(self):
        dt = datetime(2026, 10, 1, tzinfo=timezone.utc)
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Rozpočet", RequirementNecessity.REQUIRED,
                               due_at=dt)],
            eligibility=eligible(),
        ).items
        self.assertEqual(items[0].due_at, dt)

    def test_eligibility_ineligible_blocks(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[],
            eligibility=ineligible(),
        ).items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, ChecklistItemStatus.TODO)
        self.assertTrue(items[0].blocking)
        self.assertEqual(items[0].source, "ELIGIBILITY")
        self.assertEqual(items[0].reference_id, None)

    def test_eligibility_review_blocks(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[],
            eligibility=needs_review(),
        ).items
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].blocking)
        self.assertEqual(items[0].priority, 5)

    def test_eligibility_unknown_condition_generates_items(self):
        uc = ConditionEvaluation(
            condition_id="ownership",
            attribute_key="project.property_ownership",
            result=ConditionResult.UNKNOWN,
            blocking=True,
            verification_status=VerificationStatus.VERIFIED,
            actual_value=None,
            expected_value=["OWNED", "LONG_LEASE"],
            reason_code="MISSING_INPUT",
        )
        items = GEN.generate(
            workspace_id="w1",
            requirements=[],
            eligibility=needs_info(unknown_condition=uc),
        ).items
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(items[0].blocking)
        self.assertEqual(items[0].reference_id, "ownership")

    def test_empty_requirements_returns_empty(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[],
            eligibility=eligible(),
        ).items
        self.assertEqual(len(items), 0)

    def test_eligibility_none_skips(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Rozpočet", RequirementNecessity.REQUIRED)],
            eligibility=None,
        ).items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "REQUIREMENT")

    def test_eligibility_not_fully_verified_todo(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[],
            eligibility=EligibilityEvaluation(
                rule_set_id="rs1",
                status=EligibilityStatus.LIKELY_ELIGIBLE,
                root_result=ConditionResult.PASS,
                condition_results=(),
                input_snapshot_hash="a" * 64,
                evaluated_at=AT,
            ),
        ).items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].priority, 10)

    def test_mixed_necessities_produce_ordered_items(self):
        items = GEN.generate(
            workspace_id="w1",
            requirements=[
                req("r1", "Rozpočet", RequirementNecessity.REQUIRED),
                req("r2", "Doporučený", RequirementNecessity.RECOMMENDED),
                req("r3", "Povolení", RequirementNecessity.CONDITIONAL, condition_applies=False),
            ],
            eligibility=eligible(),
        ).items
        statuses = [it.status for it in items]
        self.assertIn(ChecklistItemStatus.TODO, statuses)
        self.assertIn(ChecklistItemStatus.NOT_APPLICABLE, statuses)
        self.assertEqual(len(items), 3)
        for it in items:
            if it.necessity == "REQUIRED":
                self.assertTrue(it.blocking)
            else:
                self.assertFalse(it.blocking)

    def test_diff_added_requirement(self):
        old_reqs = [req("r1", "Rozpočet", RequirementNecessity.REQUIRED)]
        new_reqs = [
            req("r1", "Rozpočet", RequirementNecessity.REQUIRED),
            req("r2", "Povolení", RequirementNecessity.CONDITIONAL, condition_applies=True),
        ]
        d = GEN.diff(workspace_id="w1", old_requirements=old_reqs, new_requirements=new_reqs)
        self.assertEqual(d.added_count, 1)
        self.assertEqual(d.removed_count, 0)
        self.assertEqual(d.changed_count, 0)
        self.assertEqual(len(d.added_items), 1)
        self.assertEqual(d.added_items[0].reference_id, "r2")

    def test_diff_removed_requirement(self):
        old_reqs = [
            req("r1", "Rozpočet", RequirementNecessity.REQUIRED),
            req("r2", "Povolení", RequirementNecessity.CONDITIONAL, condition_applies=True),
        ]
        new_reqs = [req("r1", "Rozpočet", RequirementNecessity.REQUIRED)]
        d = GEN.diff(workspace_id="w1", old_requirements=old_reqs, new_requirements=new_reqs)
        self.assertEqual(d.added_count, 0)
        self.assertEqual(d.removed_count, 1)
        self.assertEqual(len(d.removed_items), 1)
        self.assertEqual(d.removed_items[0].reference_id, "r2")

    def test_diff_changed_condition_applies(self):
        old_reqs = [req("r1", "Povolení", RequirementNecessity.CONDITIONAL, condition_applies=False)]
        new_reqs = [req("r1", "Povolení", RequirementNecessity.CONDITIONAL, condition_applies=True)]
        d = GEN.diff(workspace_id="w1", old_requirements=old_reqs, new_requirements=new_reqs)
        self.assertEqual(d.added_count, 0)
        self.assertEqual(d.removed_count, 0)
        self.assertEqual(d.changed_count, 1)
        self.assertEqual(d.changed_items[0][0].status, ChecklistItemStatus.NOT_APPLICABLE)
        self.assertEqual(d.changed_items[0][1].status, ChecklistItemStatus.TODO)

    def test_diff_unchanged_returns_zero(self):
        reqs = [req("r1", "Rozpočet", RequirementNecessity.REQUIRED)]
        d = GEN.diff(workspace_id="w1", old_requirements=reqs, new_requirements=reqs)
        self.assertEqual(d.added_count, 0)
        self.assertEqual(d.removed_count, 0)
        self.assertEqual(d.changed_count, 0)

    def test_checklist_is_immutable_tuples(self):
        checklist = GEN.generate(
            workspace_id="w1",
            requirements=[req("r1", "Rozpočet", RequirementNecessity.REQUIRED)],
            eligibility=eligible(),
        )
        self.assertIsInstance(checklist.items, tuple)
        with self.assertRaises(AttributeError):
            checklist.items[0].status = ChecklistItemStatus.DONE


if __name__ == "__main__":
    unittest.main()
