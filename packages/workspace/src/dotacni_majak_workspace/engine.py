from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from dotacni_majak_eligibility import (
    ConditionResult,
    EligibilityEvaluation,
    EligibilityStatus,
)
from dotacni_majak_finance import FinanceEvaluation, FinanceStatus


class RequirementNecessity(str, Enum):
    REQUIRED = "REQUIRED"
    CONDITIONAL = "CONDITIONAL"
    RECOMMENDED = "RECOMMENDED"


class WorkspaceTaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"


class WorkspaceTaskSource(str, Enum):
    REQUIREMENT = "REQUIREMENT"
    ELIGIBILITY = "ELIGIBILITY"
    FINANCE = "FINANCE"
    USER = "USER"


class ReadinessState(str, Enum):
    BLOCKED = "BLOCKED"
    NEEDS_ACTION = "NEEDS_ACTION"
    READY = "READY"


class WorkspaceStatus(str, Enum):
    PREPARING = "PREPARING"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    SUBMITTED = "SUBMITTED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class GrantRequirementInput:
    id: str
    title: str
    necessity: RequirementNecessity
    condition_applies: bool | None = None
    due_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceTask:
    id: str
    title: str
    source: WorkspaceTaskSource
    necessity: RequirementNecessity
    status: WorkspaceTaskStatus
    blocking: bool
    priority: int
    reference_id: str | None = None
    reason_code: str | None = None
    due_at: datetime | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessSummary:
    state: ReadinessState
    completed_count: int
    total_count: int
    completion_percent: int
    blocking_open_count: int
    next_action: WorkspaceTask | None


@dataclass(frozen=True, slots=True)
class ApplicationWorkspace:
    id: str
    project_id: str
    grant_call_id: str
    baseline_grant_version_id: str
    status: WorkspaceStatus
    tasks: tuple[WorkspaceTask, ...]

    def needs_version_review(self, current_grant_version_id: str) -> bool:
        return current_grant_version_id != self.baseline_grant_version_id


class WorkspaceEngine:
    def create(
        self,
        *,
        workspace_id: str,
        project_id: str,
        grant_call_id: str,
        baseline_grant_version_id: str,
        requirements: tuple[GrantRequirementInput, ...],
        eligibility: EligibilityEvaluation,
        finance: FinanceEvaluation,
    ) -> ApplicationWorkspace:
        tasks: list[WorkspaceTask] = []
        tasks.extend(self._requirement_tasks(workspace_id, requirements))
        tasks.extend(self._eligibility_tasks(workspace_id, eligibility))
        tasks.extend(self._finance_tasks(workspace_id, finance))

        workspace = ApplicationWorkspace(
            id=workspace_id,
            project_id=project_id,
            grant_call_id=grant_call_id,
            baseline_grant_version_id=baseline_grant_version_id,
            status=WorkspaceStatus.PREPARING,
            tasks=tuple(self._dedupe_tasks(tasks)),
        )
        return self._sync_status(workspace)

    def readiness(self, workspace: ApplicationWorkspace) -> ReadinessSummary:
        active = [
            task
            for task in workspace.tasks
            if task.status is not WorkspaceTaskStatus.NOT_APPLICABLE
        ]
        completed = [
            task for task in active if task.status is WorkspaceTaskStatus.DONE
        ]
        blocking_open = [
            task
            for task in active
            if task.blocking and task.status is not WorkspaceTaskStatus.DONE
        ]

        if any(
            task.status is WorkspaceTaskStatus.BLOCKED
            for task in blocking_open
        ):
            state = ReadinessState.BLOCKED
        elif blocking_open:
            state = ReadinessState.NEEDS_ACTION
        else:
            state = ReadinessState.READY

        percent = (
            100
            if not active
            else int(round((len(completed) / len(active)) * 100))
        )

        open_tasks = [
            task
            for task in active
            if task.status
            not in {WorkspaceTaskStatus.DONE, WorkspaceTaskStatus.NOT_APPLICABLE}
        ]
        next_action = min(
            open_tasks,
            key=lambda task: (
                0 if task.blocking else 1,
                task.priority,
                task.due_at or datetime.max,
                task.id,
            ),
            default=None,
        )

        return ReadinessSummary(
            state=state,
            completed_count=len(completed),
            total_count=len(active),
            completion_percent=percent,
            blocking_open_count=len(blocking_open),
            next_action=next_action,
        )

    def update_task_status(
        self,
        workspace: ApplicationWorkspace,
        *,
        task_id: str,
        status: WorkspaceTaskStatus,
    ) -> ApplicationWorkspace:
        found = False
        tasks: list[WorkspaceTask] = []
        for task in workspace.tasks:
            if task.id == task_id:
                found = True
                tasks.append(replace(task, status=status))
            else:
                tasks.append(task)
        if not found:
            raise KeyError(task_id)
        return self._sync_status(replace(workspace, tasks=tuple(tasks)))

    def _sync_status(
        self,
        workspace: ApplicationWorkspace,
    ) -> ApplicationWorkspace:
        if workspace.status in {
            WorkspaceStatus.SUBMITTED,
            WorkspaceStatus.ARCHIVED,
        }:
            return workspace
        readiness = self.readiness(workspace)
        status = (
            WorkspaceStatus.READY_TO_SUBMIT
            if readiness.state is ReadinessState.READY
            else WorkspaceStatus.PREPARING
        )
        return replace(workspace, status=status)

    def _requirement_tasks(
        self,
        workspace_id: str,
        requirements: tuple[GrantRequirementInput, ...],
    ) -> list[WorkspaceTask]:
        tasks: list[WorkspaceTask] = []
        for requirement in requirements:
            if requirement.necessity is RequirementNecessity.REQUIRED:
                status = WorkspaceTaskStatus.TODO
                blocking = True
                reason = "REQUIRED_BY_CALL"
            elif requirement.necessity is RequirementNecessity.CONDITIONAL:
                if requirement.condition_applies is False:
                    status = WorkspaceTaskStatus.NOT_APPLICABLE
                    blocking = False
                    reason = "CONDITION_FALSE"
                elif requirement.condition_applies is True:
                    status = WorkspaceTaskStatus.TODO
                    blocking = True
                    reason = "CONDITION_TRUE"
                else:
                    status = WorkspaceTaskStatus.TODO
                    blocking = True
                    reason = "CONDITION_UNKNOWN"
            else:
                status = WorkspaceTaskStatus.TODO
                blocking = False
                reason = "RECOMMENDED"

            tasks.append(
                WorkspaceTask(
                    id=_task_id(
                        workspace_id,
                        "requirement",
                        requirement.id,
                    ),
                    title=requirement.title,
                    source=WorkspaceTaskSource.REQUIREMENT,
                    necessity=requirement.necessity,
                    status=status,
                    blocking=blocking,
                    priority=30 if blocking else 100,
                    reference_id=requirement.id,
                    reason_code=reason,
                    due_at=requirement.due_at,
                )
            )
        return tasks

    def _eligibility_tasks(
        self,
        workspace_id: str,
        eligibility: EligibilityEvaluation,
    ) -> list[WorkspaceTask]:
        if eligibility.status is EligibilityStatus.ELIGIBLE:
            return []

        if eligibility.status is EligibilityStatus.INELIGIBLE:
            return [
                self._system_task(
                    workspace_id,
                    "eligibility-ineligible",
                    "Projekt nesplňuje ověřenou podmínku způsobilosti",
                    WorkspaceTaskSource.ELIGIBILITY,
                    WorkspaceTaskStatus.BLOCKED,
                    "ELIGIBILITY_INELIGIBLE",
                    priority=0,
                )
            ]

        if eligibility.status is EligibilityStatus.NEEDS_REVIEW:
            return [
                self._system_task(
                    workspace_id,
                    "eligibility-review",
                    "Ověřte podmínky způsobilosti, které vyžadují kontrolu",
                    WorkspaceTaskSource.ELIGIBILITY,
                    WorkspaceTaskStatus.BLOCKED,
                    "ELIGIBILITY_NEEDS_REVIEW",
                    priority=5,
                )
            ]

        if eligibility.status is EligibilityStatus.LIKELY_ELIGIBLE:
            return [
                self._system_task(
                    workspace_id,
                    "eligibility-completeness",
                    "Ověřte zbývající podmínky způsobilosti",
                    WorkspaceTaskSource.ELIGIBILITY,
                    WorkspaceTaskStatus.TODO,
                    "ELIGIBILITY_NOT_FULLY_VERIFIED",
                    priority=10,
                )
            ]

        unknowns = [
            item
            for item in eligibility.condition_results
            if item.result is ConditionResult.UNKNOWN and item.blocking
        ]
        if unknowns:
            return [
                self._system_task(
                    workspace_id,
                    f"eligibility:{item.condition_id}",
                    f"Doplňte údaj: {item.attribute_key}",
                    WorkspaceTaskSource.ELIGIBILITY,
                    WorkspaceTaskStatus.TODO,
                    item.reason_code,
                    priority=10,
                    reference_id=item.condition_id,
                )
                for item in unknowns
            ]

        return [
            self._system_task(
                workspace_id,
                "eligibility-missing-information",
                "Doplňte informace potřebné k ověření způsobilosti",
                WorkspaceTaskSource.ELIGIBILITY,
                WorkspaceTaskStatus.TODO,
                "ELIGIBILITY_NEEDS_INFORMATION",
                priority=10,
            )
        ]

    def _finance_tasks(
        self,
        workspace_id: str,
        finance: FinanceEvaluation,
    ) -> list[WorkspaceTask]:
        if finance.status is FinanceStatus.COMPLETE:
            return []

        if finance.status is FinanceStatus.SCENARIO_NOT_APPLICABLE:
            return [
                self._system_task(
                    workspace_id,
                    "finance-not-applicable",
                    "Financování projektu neodpovídá známým limitům výzvy",
                    WorkspaceTaskSource.FINANCE,
                    WorkspaceTaskStatus.BLOCKED,
                    "FINANCE_SCENARIO_NOT_APPLICABLE",
                    priority=1,
                )
            ]

        if finance.status is FinanceStatus.INSTRUMENT_NOT_SUPPORTED:
            return [
                self._system_task(
                    workspace_id,
                    "finance-instrument-not-supported",
                    "Tento typ podpory vyžaduje specializovaný finanční výpočet",
                    WorkspaceTaskSource.FINANCE,
                    WorkspaceTaskStatus.BLOCKED,
                    "FINANCE_INSTRUMENT_NOT_SUPPORTED",
                    priority=5,
                )
            ]

        if finance.status is FinanceStatus.ERROR:
            return [
                self._system_task(
                    workspace_id,
                    "finance-error",
                    "Finanční podmínky potřebují kontrolu",
                    WorkspaceTaskSource.FINANCE,
                    WorkspaceTaskStatus.BLOCKED,
                    "FINANCE_ERROR",
                    priority=5,
                )
            ]

        tasks: list[WorkspaceTask] = []
        for reason in finance.reason_codes:
            if not reason.startswith("MISSING_"):
                continue
            tasks.append(
                self._system_task(
                    workspace_id,
                    f"finance:{reason}",
                    _finance_missing_title(reason),
                    WorkspaceTaskSource.FINANCE,
                    WorkspaceTaskStatus.TODO,
                    reason,
                    priority=20,
                )
            )

        return tasks or [
            self._system_task(
                workspace_id,
                "finance-missing-information",
                "Doplňte informace potřebné k výpočtu financování",
                WorkspaceTaskSource.FINANCE,
                WorkspaceTaskStatus.TODO,
                "FINANCE_NEEDS_INFORMATION",
                priority=20,
            )
        ]

    @staticmethod
    def _system_task(
        workspace_id: str,
        identity: str,
        title: str,
        source: WorkspaceTaskSource,
        status: WorkspaceTaskStatus,
        reason_code: str,
        *,
        priority: int,
        reference_id: str | None = None,
    ) -> WorkspaceTask:
        return WorkspaceTask(
            id=_task_id(workspace_id, source.value, identity),
            title=title,
            source=source,
            necessity=RequirementNecessity.REQUIRED,
            status=status,
            blocking=True,
            priority=priority,
            reference_id=reference_id,
            reason_code=reason_code,
        )

    @staticmethod
    def _dedupe_tasks(
        tasks: list[WorkspaceTask],
    ) -> list[WorkspaceTask]:
        by_id: dict[str, WorkspaceTask] = {}
        for task in tasks:
            by_id[task.id] = task
        return sorted(by_id.values(), key=lambda task: (task.priority, task.id))


def _task_id(workspace_id: str, source: str, identity: str) -> str:
    digest = hashlib.sha256(
        f"{workspace_id}\x1f{source}\x1f{identity}".encode("utf-8")
    ).hexdigest()
    return f"tsk_{digest[:24]}"


def _finance_missing_title(reason: str) -> str:
    return {
        "MISSING_ELIGIBLE_COSTS": "Doplňte způsobilé náklady projektu",
        "MISSING_INELIGIBLE_COSTS": "Doplňte nezpůsobilé náklady projektu",
        "MISSING_NONRECOVERABLE_VAT": "Ověřte zacházení s DPH",
        "MISSING_TOTAL_PROJECT_COST": "Doplňte celkový rozpočet projektu",
        "MISSING_SUPPORT_RATE_MAX": "Ověřte maximální míru podpory",
    }.get(
        reason,
        "Doplňte chybějící finanční údaj",
    )
