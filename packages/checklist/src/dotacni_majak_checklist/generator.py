from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence

from dotacni_majak_eligibility import EligibilityEvaluation, EligibilityStatus
from dotacni_majak_workspace import GrantRequirementInput, RequirementNecessity


class ChecklistItemStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    id: str
    title: str
    necessity: str  # REQUIRED, CONDITIONAL, RECOMMENDED
    status: ChecklistItemStatus
    source: str  # REQUIREMENT | ELIGIBILITY
    blocking: bool
    priority: int
    reference_id: str | None = None
    evidence_id: str | None = None
    due_at: datetime | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Checklist:
    items: tuple[ChecklistItem, ...]


@dataclass(frozen=True, slots=True)
class ChecklistDiff:
    added_count: int
    removed_count: int
    changed_count: int
    added_items: list[ChecklistItem]
    removed_items: list[ChecklistItem]
    changed_items: list[tuple[ChecklistItem, ChecklistItem]]  # (old, new)


class RequirementChecklistGenerator:
    """Generate a requirement checklist from documented GrantRequirement inputs
    and an optional eligibility evaluation.

    Produces a checklist with explicit items per documented requirement,
    honoring REQUIRED / CONDITIONAL / RECOMMENDED distinctions and linking
    to evidence where provided. Supports regeneration diff between two
    requirement sets.
    """

    def __init__(self) -> None:
        pass

    def generate(
        self,
        *,
        workspace_id: str,
        requirements: Sequence[GrantRequirementInput],
        eligibility: EligibilityEvaluation | None = None,
    ) -> Checklist:
        items: list[ChecklistItem] = []
        items.extend(self._requirement_items(workspace_id, requirements))
        if eligibility is not None:
            items.extend(self._eligibility_items(workspace_id, eligibility))
        return Checklist(items=tuple(items))

    def diff(
        self,
        *,
        workspace_id: str,
        old_requirements: Sequence[GrantRequirementInput],
        new_requirements: Sequence[GrantRequirementInput],
    ) -> ChecklistDiff:
        old_items = {
            item.id: item
            for item in self._requirement_items(workspace_id, old_requirements)
        }
        new_items = {
            item.id: item
            for item in self._requirement_items(workspace_id, new_requirements)
        }

        old_ids = set(old_items.keys())
        new_ids = set(new_items.keys())

        added_ids = new_ids - old_ids
        removed_ids = old_ids - new_ids
        common_ids = old_ids & new_ids

        changed: list[tuple[ChecklistItem, ChecklistItem]] = []
        for cid in common_ids:
            old_item = old_items[cid]
            new_item = new_items[cid]
            if old_item != new_item:
                changed.append((old_item, new_item))

        return ChecklistDiff(
            added_count=len(added_ids),
            removed_count=len(removed_ids),
            changed_count=len(changed),
            added_items=[new_items[cid] for cid in sorted(added_ids)],
            removed_items=[old_items[cid] for cid in sorted(removed_ids)],
            changed_items=sorted(
                changed,
                key=lambda pair: (pair[0].priority, pair[0].id),
            ),
        )

    def _requirement_items(
        self,
        workspace_id: str,
        requirements: Sequence[GrantRequirementInput],
    ) -> list[ChecklistItem]:
        items: list[ChecklistItem] = []
        for req in requirements:
            if req.necessity is RequirementNecessity.REQUIRED:
                status = ChecklistItemStatus.TODO
                blocking = True
                priority = 30
            elif req.necessity is RequirementNecessity.CONDITIONAL:
                if req.condition_applies is False:
                    status = ChecklistItemStatus.NOT_APPLICABLE
                    blocking = False
                    priority = 100
                elif req.condition_applies is True:
                    status = ChecklistItemStatus.TODO
                    blocking = True
                    priority = 30
                else:
                    status = ChecklistItemStatus.TODO
                    blocking = True
                    priority = 30
            else:  # RECOMMENDED
                status = ChecklistItemStatus.TODO
                blocking = False
                priority = 100

            items.append(
                ChecklistItem(
                    id=_item_id(workspace_id, "requirement", req.id),
                    title=req.title,
                    necessity=req.necessity.value,
                    status=status,
                    source="REQUIREMENT",
                    blocking=blocking,
                    priority=priority,
                    reference_id=req.id,
                    evidence_id=None,
                    due_at=req.due_at,
                )
            )
        return items

    def _eligibility_items(
        self,
        workspace_id: str,
        eligibility: EligibilityEvaluation,
    ) -> list[ChecklistItem]:
        from dotacni_majak_eligibility import ConditionResult

        if eligibility.status is EligibilityStatus.ELIGIBLE:
            return []

        if eligibility.status is EligibilityStatus.INELIGIBLE:
            return [self._system_item(workspace_id, "eligibility-ineligible",
                "Projekt nesplňuje ověřenou podmínku způsobilosti",
                "ELIGIBILITY_INELIGIBLE", priority=0)]

        if eligibility.status is EligibilityStatus.NEEDS_REVIEW:
            return [self._system_item(workspace_id, "eligibility-review",
                "Ověřte podmínky způsobilosti, které vyžadují kontrolu",
                "ELIGIBILITY_NEEDS_REVIEW", priority=5)]

        if eligibility.status is EligibilityStatus.LIKELY_ELIGIBLE:
            return [self._system_item(workspace_id, "eligibility-completeness",
                "Ověřte zbývající podmínky způsobilosti",
                "ELIGIBILITY_NOT_FULLY_VERIFIED", priority=10)]

        unknowns = [item for item in eligibility.condition_results
                    if item.result is ConditionResult.UNKNOWN and item.blocking]
        if unknowns:
            return [
                self._system_item(workspace_id,
                    f"eligibility:{item.condition_id}",
                    f"Doplňte údaj: {item.attribute_key}",
                    item.reason_code, priority=10,
                    reference_id=item.condition_id)
                for item in unknowns
            ]

        return [self._system_item(workspace_id, "eligibility-missing-information",
            "Doplňte informace potřebné k ověření způsobilosti",
            "ELIGIBILITY_NEEDS_INFORMATION", priority=10)]

    @staticmethod
    def _system_item(
        workspace_id: str,
        identity: str,
        title: str,
        reason_code: str,
        *,
        priority: int,
        reference_id: str | None = None,
    ) -> ChecklistItem:
        return ChecklistItem(
            id=_item_id(workspace_id, "system", identity),
            title=title,
            necessity="REQUIRED",
            status=ChecklistItemStatus.TODO,
            source="ELIGIBILITY",
            blocking=True,
            priority=priority,
            reference_id=reference_id,
            evidence_id=None,
            due_at=None,
            note=None,
        )


def _item_id(workspace_id: str, source: str, identity: str) -> str:
    digest = hashlib.sha256(
        f"{workspace_id}\x1f{source}\x1f{identity}".encode("utf-8")
    ).hexdigest()
    return f"chk_{digest[:24]}"
