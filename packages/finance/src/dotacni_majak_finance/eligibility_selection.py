"""Fail-closed bridge from a same-version eligibility evaluation to finance selection.

This is a domain adapter, not a D1 loader or a public finance calculation API.
Callers must load the immutable rule set, funding scenarios and field evidence
from the same canonical grant-call version before invoking it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Mapping

from .engine import FinanceEngine, FinanceStatus, FundingScenario, ScenarioApplicability

if TYPE_CHECKING:
    from dotacni_majak_eligibility import EligibilityEvaluator, RuleSet


@dataclass(frozen=True, slots=True)
class VersionedFundingScenario:
    scenario: FundingScenario
    grant_call_version_id: str


@dataclass(frozen=True, slots=True)
class VerifiedScenarioSelection:
    status: FinanceStatus
    scenario: FundingScenario | None
    reason_codes: tuple[str, ...]
    rule_set_id: str
    grant_call_version_id: str
    # References to canonical field_evidence, not a copy of applicant values.
    evidence_ids_by_group: Mapping[str, tuple[str, ...]]


def select_from_eligibility(
    *,
    grant_call_version_id: str,
    rule_set_grant_call_version_id: str,
    rule_set: RuleSet,
    scenarios: tuple[VersionedFundingScenario, ...] | list[VersionedFundingScenario],
    values: dict[str, Any],
    field_evidence_ids_by_condition: Mapping[str, str],
    evaluator: EligibilityEvaluator,
    finance_engine: FinanceEngine,
) -> VerifiedScenarioSelection:
    """Evaluate the actual rule tree, then select only verified, evidenced groups.

    The version IDs and evidence references are supplied by the trusted D1 loader;
    this function checks their agreement, but cannot independently authenticate D1.
    Unknown, partial, unverified, missing evidence or unlinked conditions never
    become an applicant-specific PASS/FAIL. No financial amount is calculated.
    """
    from dotacni_majak_eligibility import (
        CompletenessStatus,
        ConditionResult,
        VerificationStatus,
    )

    def blocked(reason: str) -> VerifiedScenarioSelection:
        return VerifiedScenarioSelection(
            status=FinanceStatus.ERROR,
            scenario=None,
            reason_codes=(reason,),
            rule_set_id=rule_set.id,
            grant_call_version_id=grant_call_version_id,
            evidence_ids_by_group={},
        )

    if (
        not grant_call_version_id
        or rule_set_grant_call_version_id != grant_call_version_id
        or any(item.grant_call_version_id != grant_call_version_id for item in scenarios)
    ):
        return blocked("GRANT_CALL_VERSION_MISMATCH")
    if not rule_set.id:
        return blocked("RULE_SET_ID_MISSING")
    if any(not isinstance(item.scenario.applicability, ScenarioApplicability) for item in scenarios):
        return blocked("INVALID_SCENARIO_APPLICABILITY")

    evaluation = evaluator.evaluate(rule_set, values)
    if evaluation.rule_set_id != rule_set.id:
        return blocked("RULE_SET_ID_MISMATCH")
    if evaluation.root_result is ConditionResult.ERROR or any(
        item.result is ConditionResult.ERROR for item in evaluation.condition_results
    ):
        return blocked("ELIGIBILITY_EVALUATION_ERROR")

    conditions = {item.condition_id: item for item in evaluation.condition_results}
    if len(conditions) != len(evaluation.condition_results):
        return blocked("DUPLICATE_CONDITION_ID")
    groups = {item.group_id: item for item in evaluation.group_results}
    if len(groups) != len(evaluation.group_results):
        return blocked("DUPLICATE_GROUP_ID")

    group_results: dict[str, ScenarioApplicability] = {}
    evidence_by_group: dict[str, tuple[str, ...]] = {}
    trusted_rule_set = (
        rule_set.completeness_status is CompletenessStatus.COMPLETE
        and rule_set.verification_status is VerificationStatus.VERIFIED
    )
    for group_id, group in groups.items():
        descendants = [conditions.get(identifier) for identifier in group.condition_ids]
        trusted_conditions = bool(descendants) and all(
            condition is not None
            and condition.verification_status is VerificationStatus.VERIFIED
            and condition.result in (ConditionResult.PASS, ConditionResult.FAIL)
            and isinstance(field_evidence_ids_by_condition.get(condition.condition_id), str)
            and bool(field_evidence_ids_by_condition[condition.condition_id].strip())
            for condition in descendants
        )
        if trusted_rule_set and trusted_conditions and group.result in (
            ConditionResult.PASS, ConditionResult.FAIL,
        ):
            group_results[group_id] = ScenarioApplicability(group.result.value)
            evidence_by_group[group_id] = tuple(
                field_evidence_ids_by_condition[identifier]
                for identifier in group.condition_ids
            )
        else:
            group_results[group_id] = ScenarioApplicability.UNKNOWN

    # Stored applicability has no per-applicant evidence at this boundary.
    # In particular, an inherited FAIL must not exclude a competing scenario
    # when its linked group is UNKNOWN. Only an evidenced group FAIL may do so.
    candidates = [
        replace(
            item.scenario,
            applicability=(
                ScenarioApplicability.PASS
                if item.scenario.condition_group_id is not None
                and item.scenario.applicability is ScenarioApplicability.PASS
                and group_results.get(item.scenario.condition_group_id)
                in (ScenarioApplicability.PASS, ScenarioApplicability.FAIL)
                else ScenarioApplicability.UNKNOWN
            ),
        )
        for item in scenarios
    ]
    status, selected, reasons = finance_engine.select_scenario(
        candidates, group_results=group_results,
    )
    if status is FinanceStatus.COMPLETE and selected is not None:
        selected = next(item.scenario for item in scenarios if item.scenario.id == selected.id)
    return VerifiedScenarioSelection(
        status=status,
        scenario=selected,
        reason_codes=reasons,
        rule_set_id=rule_set.id,
        grant_call_version_id=grant_call_version_id,
        evidence_ids_by_group=evidence_by_group,
    )
