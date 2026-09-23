from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ChangeType(str, Enum):
    DEADLINE_CHANGED = "DEADLINE_CHANGED"
    STATUS_CHANGED = "STATUS_CHANGED"
    APPLICANT_RULE_CHANGED = "APPLICANT_RULE_CHANGED"
    FUNDING_CHANGED = "FUNDING_CHANGED"
    BUDGET_CHANGED = "BUDGET_CHANGED"
    SUPPORTED_ACTIVITY_CHANGED = "SUPPORTED_ACTIVITY_CHANGED"
    REQUIREMENT_CHANGED = "REQUIREMENT_CHANGED"
    DOCUMENT_CHANGED = "DOCUMENT_CHANGED"
    OTHER = "OTHER"


class ChangeSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    IMPORTANT = "IMPORTANT"
    INFORMATIONAL = "INFORMATIONAL"
    EDITORIAL = "EDITORIAL"


@dataclass(frozen=True, slots=True)
class FundingState:
    support_rate_min_bps: int | None = None
    support_rate_max_bps: int | None = None
    grant_amount_min_minor: int | None = None
    grant_amount_max_minor: int | None = None
    project_cost_min_minor: int | None = None
    project_cost_max_minor: int | None = None
    payment_mode: str | None = None
    advance_payment_allowed: bool | None = None


@dataclass(frozen=True, slots=True)
class RequirementState:
    title: str
    necessity: str
    requirement_type: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class GrantVersionState:
    status: str
    title: str
    summary: str | None = None
    submission_open_at: str | None = None
    submission_close_at: str | None = None
    applicant_rules_fingerprint: str | None = None
    applicant_rules_summary: Any = None
    funding: Mapping[str, FundingState] = field(default_factory=dict)
    supported_activities: frozenset[str] = field(default_factory=frozenset)
    requirements: Mapping[str, RequirementState] = field(default_factory=dict)
    documents: Mapping[str, str] = field(default_factory=dict)
    evidence_by_field: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    id: str
    grant_call_id: str
    from_version_id: str
    to_version_id: str
    change_type: ChangeType
    severity: ChangeSeverity
    field_path: str
    old_value: Any
    new_value: Any
    evidence_id: str | None
    created_at: datetime


class ChangeDetector:
    def detect(
        self,
        *,
        grant_call_id: str,
        from_version_id: str,
        to_version_id: str,
        old: GrantVersionState,
        new: GrantVersionState,
        created_at: datetime | None = None,
    ) -> tuple[ChangeEvent, ...]:
        if from_version_id == to_version_id:
            raise ValueError("from_version_id and to_version_id must differ")
        at = created_at or datetime.now(timezone.utc)
        events: list[ChangeEvent] = []

        self._add_if_changed(
            events, grant_call_id, from_version_id, to_version_id,
            "status", old.status, new.status,
            ChangeType.STATUS_CHANGED,
            (
                ChangeSeverity.CRITICAL
                if new.status in {"PAUSED", "CLOSED", "CANCELLED"}
                else ChangeSeverity.IMPORTANT
            ),
            old, new, at,
        )
        self._add_if_changed(
            events, grant_call_id, from_version_id, to_version_id,
            "deadlines.application_open",
            old.submission_open_at, new.submission_open_at,
            ChangeType.DEADLINE_CHANGED, ChangeSeverity.CRITICAL,
            old, new, at,
        )
        self._add_if_changed(
            events, grant_call_id, from_version_id, to_version_id,
            "deadlines.application_close",
            old.submission_close_at, new.submission_close_at,
            ChangeType.DEADLINE_CHANGED, ChangeSeverity.CRITICAL,
            old, new, at,
        )
        self._add_if_changed(
            events, grant_call_id, from_version_id, to_version_id,
            "eligibility.applicant_rules",
            old.applicant_rules_fingerprint,
            new.applicant_rules_fingerprint,
            ChangeType.APPLICANT_RULE_CHANGED,
            ChangeSeverity.CRITICAL,
            old, new, at,
            old_display=old.applicant_rules_summary,
            new_display=new.applicant_rules_summary,
        )

        self._diff_funding(
            events, grant_call_id, from_version_id, to_version_id,
            old, new, at,
        )
        self._diff_set(
            events, grant_call_id, from_version_id, to_version_id,
            "supported_activities",
            old.supported_activities,
            new.supported_activities,
            ChangeType.SUPPORTED_ACTIVITY_CHANGED,
            ChangeSeverity.IMPORTANT,
            old, new, at,
        )
        self._diff_mapping(
            events, grant_call_id, from_version_id, to_version_id,
            "requirements",
            old.requirements,
            new.requirements,
            ChangeType.REQUIREMENT_CHANGED,
            ChangeSeverity.IMPORTANT,
            old, new, at,
        )
        self._diff_mapping(
            events, grant_call_id, from_version_id, to_version_id,
            "documents",
            old.documents,
            new.documents,
            ChangeType.DOCUMENT_CHANGED,
            ChangeSeverity.INFORMATIONAL,
            old, new, at,
        )
        self._add_if_changed(
            events, grant_call_id, from_version_id, to_version_id,
            "title", old.title, new.title,
            ChangeType.OTHER, ChangeSeverity.EDITORIAL,
            old, new, at,
        )
        self._add_if_changed(
            events, grant_call_id, from_version_id, to_version_id,
            "summary", old.summary, new.summary,
            ChangeType.OTHER, ChangeSeverity.EDITORIAL,
            old, new, at,
        )

        # Stable field ordering makes output deterministic and easier to test.
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    _severity_order(event.severity),
                    event.field_path,
                    event.id,
                ),
            )
        )

    def _diff_funding(
        self,
        events: list[ChangeEvent],
        grant_call_id: str,
        from_version_id: str,
        to_version_id: str,
        old: GrantVersionState,
        new: GrantVersionState,
        at: datetime,
    ) -> None:
        scenario_ids = sorted(set(old.funding) | set(new.funding))
        for scenario_id in scenario_ids:
            old_scenario = old.funding.get(scenario_id)
            new_scenario = new.funding.get(scenario_id)
            base = f"funding.{scenario_id}"

            if old_scenario is None or new_scenario is None:
                self._append(
                    events, grant_call_id, from_version_id, to_version_id,
                    base,
                    _jsonable(old_scenario),
                    _jsonable(new_scenario),
                    ChangeType.FUNDING_CHANGED,
                    ChangeSeverity.CRITICAL,
                    old, new, at,
                )
                continue

            for field_name in (
                "support_rate_min_bps",
                "support_rate_max_bps",
                "grant_amount_min_minor",
                "grant_amount_max_minor",
                "payment_mode",
                "advance_payment_allowed",
            ):
                self._add_if_changed(
                    events, grant_call_id, from_version_id, to_version_id,
                    f"{base}.{field_name}",
                    getattr(old_scenario, field_name),
                    getattr(new_scenario, field_name),
                    ChangeType.FUNDING_CHANGED,
                    ChangeSeverity.CRITICAL,
                    old, new, at,
                )

            for field_name in (
                "project_cost_min_minor",
                "project_cost_max_minor",
            ):
                self._add_if_changed(
                    events, grant_call_id, from_version_id, to_version_id,
                    f"{base}.{field_name}",
                    getattr(old_scenario, field_name),
                    getattr(new_scenario, field_name),
                    ChangeType.BUDGET_CHANGED,
                    ChangeSeverity.CRITICAL,
                    old, new, at,
                )

    def _diff_set(
        self,
        events: list[ChangeEvent],
        grant_call_id: str,
        from_version_id: str,
        to_version_id: str,
        path: str,
        old_values: frozenset[str],
        new_values: frozenset[str],
        change_type: ChangeType,
        severity: ChangeSeverity,
        old_state: GrantVersionState,
        new_state: GrantVersionState,
        at: datetime,
    ) -> None:
        if old_values == new_values:
            return
        self._append(
            events, grant_call_id, from_version_id, to_version_id,
            path,
            sorted(old_values),
            sorted(new_values),
            change_type, severity, old_state, new_state, at,
        )

    def _diff_mapping(
        self,
        events: list[ChangeEvent],
        grant_call_id: str,
        from_version_id: str,
        to_version_id: str,
        path: str,
        old_values: Mapping[str, Any],
        new_values: Mapping[str, Any],
        change_type: ChangeType,
        severity: ChangeSeverity,
        old_state: GrantVersionState,
        new_state: GrantVersionState,
        at: datetime,
    ) -> None:
        for key in sorted(set(old_values) | set(new_values)):
            old_value = old_values.get(key)
            new_value = new_values.get(key)
            if old_value == new_value:
                continue
            self._append(
                events, grant_call_id, from_version_id, to_version_id,
                f"{path}.{key}",
                _jsonable(old_value),
                _jsonable(new_value),
                change_type, severity, old_state, new_state, at,
            )

    def _add_if_changed(
        self,
        events: list[ChangeEvent],
        grant_call_id: str,
        from_version_id: str,
        to_version_id: str,
        path: str,
        old_value: Any,
        new_value: Any,
        change_type: ChangeType,
        severity: ChangeSeverity,
        old_state: GrantVersionState,
        new_state: GrantVersionState,
        at: datetime,
        *,
        old_display: Any = None,
        new_display: Any = None,
    ) -> None:
        if old_value == new_value:
            return
        self._append(
            events, grant_call_id, from_version_id, to_version_id,
            path,
            old_value if old_display is None else old_display,
            new_value if new_display is None else new_display,
            change_type, severity, old_state, new_state, at,
        )

    def _append(
        self,
        events: list[ChangeEvent],
        grant_call_id: str,
        from_version_id: str,
        to_version_id: str,
        path: str,
        old_value: Any,
        new_value: Any,
        change_type: ChangeType,
        severity: ChangeSeverity,
        old_state: GrantVersionState,
        new_state: GrantVersionState,
        at: datetime,
    ) -> None:
        evidence_id = (
            new_state.evidence_by_field.get(path)
            or old_state.evidence_by_field.get(path)
        )
        event_id = _event_id(
            grant_call_id,
            from_version_id,
            to_version_id,
            change_type.value,
            path,
        )
        events.append(
            ChangeEvent(
                id=event_id,
                grant_call_id=grant_call_id,
                from_version_id=from_version_id,
                to_version_id=to_version_id,
                change_type=change_type,
                severity=severity,
                field_path=path,
                old_value=_jsonable(old_value),
                new_value=_jsonable(new_value),
                evidence_id=evidence_id,
                created_at=at,
            )
        )


def _event_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"chg_{digest[:24]}"


def _severity_order(value: ChangeSeverity) -> int:
    return {
        ChangeSeverity.CRITICAL: 0,
        ChangeSeverity.IMPORTANT: 1,
        ChangeSeverity.INFORMATIONAL: 2,
        ChangeSeverity.EDITORIAL: 3,
    }[value]


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: _jsonable(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, (set, frozenset, tuple)):
        return [_jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _jsonable(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value
