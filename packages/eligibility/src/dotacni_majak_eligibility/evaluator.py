from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Protocol, TypeAlias


class ConditionResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class GroupOperator(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class ConditionOperator(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    IN = "IN"
    NOT_IN = "NOT_IN"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    BETWEEN = "BETWEEN"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    CONTAINS = "CONTAINS"
    INTERSECTS = "INTERSECTS"
    DATE_BEFORE = "DATE_BEFORE"
    DATE_AFTER = "DATE_AFTER"
    GEO_WITHIN = "GEO_WITHIN"
    GEO_NOT_WITHIN = "GEO_NOT_WITHIN"


class UnknownPolicy(str, Enum):
    PROPAGATE = "PROPAGATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VerificationStatus(str, Enum):
    AUTO_EXTRACTED = "AUTO_EXTRACTED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class CompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class AttributeDataType(str, Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    MONEY_MINOR = "MONEY_MINOR"
    PERCENT_BPS = "PERCENT_BPS"
    ENUM = "ENUM"
    GEO_ID = "GEO_ID"
    STRING_SET = "STRING_SET"


class KnownAbsentType:
    __slots__ = ()

    def __repr__(self) -> str:
        return "KNOWN_ABSENT"


KNOWN_ABSENT = KnownAbsentType()
_MISSING = object()


class GeographyResolver(Protocol):
    def is_within(
        self,
        actual_geography_id: str,
        expected_geography_id: str,
    ) -> bool | None: ...


@dataclass(frozen=True, slots=True)
class AttributeDefinition:
    id: str
    key: str
    data_type: AttributeDataType


@dataclass(frozen=True, slots=True)
class RuleCondition:
    id: str
    attribute: AttributeDefinition
    operator: ConditionOperator
    expected_value: Any = None
    blocking: bool = True
    unknown_policy: UnknownPolicy = UnknownPolicy.PROPAGATE
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


@dataclass(frozen=True, slots=True)
class RuleGroup:
    id: str
    operator: GroupOperator
    children: tuple["RuleNode", ...]


RuleNode: TypeAlias = RuleCondition | RuleGroup


@dataclass(frozen=True, slots=True)
class RuleSet:
    id: str
    root: RuleGroup
    completeness_status: CompletenessStatus = CompletenessStatus.UNKNOWN
    verification_status: VerificationStatus = VerificationStatus.NEEDS_REVIEW


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    condition_id: str
    attribute_key: str
    result: ConditionResult
    blocking: bool
    verification_status: VerificationStatus
    actual_value: Any
    expected_value: Any
    reason_code: str


@dataclass(frozen=True, slots=True)
class EligibilityEvaluation:
    rule_set_id: str
    status: EligibilityStatus
    root_result: ConditionResult
    condition_results: tuple[ConditionEvaluation, ...]
    input_snapshot_hash: str
    evaluated_at: datetime
    engine_version: str = "eligibility-v1"

    @property
    def counts(self) -> dict[str, int]:
        result = {item.value: 0 for item in ConditionResult}
        for item in self.condition_results:
            result[item.result.value] += 1
        return result


class RuleDefinitionError(ValueError):
    pass


class EligibilityEvaluator:
    def __init__(
        self,
        *,
        geography: GeographyResolver | None = None,
        engine_version: str = "eligibility-v1",
    ) -> None:
        self.geography = geography
        self.engine_version = engine_version

    def evaluate(
        self,
        rule_set: RuleSet,
        values: dict[str, Any],
        *,
        evaluated_at: datetime | None = None,
    ) -> EligibilityEvaluation:
        at = evaluated_at or datetime.now(timezone.utc)
        condition_results: list[ConditionEvaluation] = []

        try:
            self._validate_group(rule_set.root)
            root_result = self._evaluate_group(
                rule_set.root,
                values,
                condition_results,
            )
        except RuleDefinitionError as exc:
            condition_results.append(
                ConditionEvaluation(
                    condition_id="__rule_definition__",
                    attribute_key="__rule_definition__",
                    result=ConditionResult.ERROR,
                    blocking=True,
                    verification_status=VerificationStatus.NEEDS_REVIEW,
                    actual_value=None,
                    expected_value=None,
                    reason_code=f"RULE_DEFINITION_ERROR:{exc}",
                )
            )
            root_result = ConditionResult.ERROR

        status = self._public_status(
            rule_set,
            root_result,
            condition_results,
        )
        return EligibilityEvaluation(
            rule_set_id=rule_set.id,
            status=status,
            root_result=root_result,
            condition_results=tuple(condition_results),
            input_snapshot_hash=_snapshot_hash(values),
            evaluated_at=at,
            engine_version=self.engine_version,
        )

    def _validate_group(self, group: RuleGroup) -> None:
        if not group.children:
            raise RuleDefinitionError(f"group {group.id!r} has no children")
        if group.operator is GroupOperator.NOT and len(group.children) != 1:
            raise RuleDefinitionError(
                f"NOT group {group.id!r} must contain exactly one child"
            )
        for child in group.children:
            if isinstance(child, RuleGroup):
                self._validate_group(child)

    def _evaluate_group(
        self,
        group: RuleGroup,
        values: dict[str, Any],
        condition_results: list[ConditionEvaluation],
    ) -> ConditionResult:
        results: list[ConditionResult] = []
        for child in group.children:
            if isinstance(child, RuleGroup):
                results.append(
                    self._evaluate_group(child, values, condition_results)
                )
                continue

            evaluated = self._evaluate_condition(child, values)
            condition_results.append(evaluated)
            results.append(
                evaluated.result
                if child.blocking
                else ConditionResult.NOT_APPLICABLE
            )

        if group.operator is GroupOperator.NOT:
            return _negate(results[0])
        if group.operator is GroupOperator.AND:
            return _and(results)
        if group.operator is GroupOperator.OR:
            return _or(results)
        raise RuleDefinitionError(f"unsupported group operator {group.operator}")

    def _evaluate_condition(
        self,
        condition: RuleCondition,
        values: dict[str, Any],
    ) -> ConditionEvaluation:
        actual = values.get(condition.attribute.key, _MISSING)
        if actual is _MISSING or actual is None:
            result = (
                ConditionResult.NOT_APPLICABLE
                if condition.unknown_policy is UnknownPolicy.NOT_APPLICABLE
                else ConditionResult.UNKNOWN
            )
            return self._condition_result(
                condition,
                result,
                None,
                "MISSING_INPUT",
            )

        if actual is KNOWN_ABSENT:
            if condition.operator is ConditionOperator.EXISTS:
                return self._condition_result(
                    condition,
                    ConditionResult.FAIL,
                    {"$absent": True},
                    "KNOWN_ABSENT",
                )
            if condition.operator is ConditionOperator.NOT_EXISTS:
                return self._condition_result(
                    condition,
                    ConditionResult.PASS,
                    {"$absent": True},
                    "KNOWN_ABSENT",
                )
            return self._condition_result(
                condition,
                ConditionResult.UNKNOWN,
                {"$absent": True},
                "KNOWN_ABSENT_NOT_COMPARABLE",
            )

        try:
            coerced_actual = _coerce(
                actual,
                condition.attribute.data_type,
            )
            result = self._apply_operator(
                condition,
                coerced_actual,
            )
            return self._condition_result(
                condition,
                result,
                _jsonable(coerced_actual),
                "EVALUATED",
            )
        except (TypeError, ValueError) as exc:
            return self._condition_result(
                condition,
                ConditionResult.ERROR,
                _jsonable(actual),
                f"TYPE_OR_RULE_ERROR:{type(exc).__name__}:{exc}",
            )

    def _apply_operator(
        self,
        condition: RuleCondition,
        actual: Any,
    ) -> ConditionResult:
        op = condition.operator
        expected = condition.expected_value
        data_type = condition.attribute.data_type

        if op is ConditionOperator.EXISTS:
            return ConditionResult.PASS
        if op is ConditionOperator.NOT_EXISTS:
            return ConditionResult.FAIL

        if op in (
            ConditionOperator.GEO_WITHIN,
            ConditionOperator.GEO_NOT_WITHIN,
        ):
            if data_type is not AttributeDataType.GEO_ID:
                raise TypeError("geography operator requires GEO_ID")
            if self.geography is None:
                return ConditionResult.UNKNOWN
            expected_geo = _coerce(expected, AttributeDataType.GEO_ID)
            within = self.geography.is_within(actual, expected_geo)
            if within is None:
                return ConditionResult.UNKNOWN
            if op is ConditionOperator.GEO_NOT_WITHIN:
                within = not within
            return _bool_result(within)

        if op in (
            ConditionOperator.DATE_BEFORE,
            ConditionOperator.DATE_AFTER,
        ):
            if data_type not in (
                AttributeDataType.DATE,
                AttributeDataType.DATETIME,
            ):
                raise TypeError("date operator requires DATE/DATETIME")
            expected_value = _coerce(expected, data_type)
            return _bool_result(
                actual < expected_value
                if op is ConditionOperator.DATE_BEFORE
                else actual > expected_value
            )

        if op is ConditionOperator.BETWEEN:
            if not isinstance(expected, (list, tuple)) or len(expected) != 2:
                raise ValueError("BETWEEN expects exactly two values")
            lower = _coerce(expected[0], data_type)
            upper = _coerce(expected[1], data_type)
            if lower > upper:
                raise ValueError("BETWEEN lower bound exceeds upper bound")
            return _bool_result(lower <= actual <= upper)

        if op in (
            ConditionOperator.IN,
            ConditionOperator.NOT_IN,
        ):
            if not isinstance(expected, (list, tuple, set, frozenset)):
                raise TypeError("IN/NOT_IN expects an array/set")
            expected_values = {
                _coerce(item, data_type)
                for item in expected
            }
            matched = actual in expected_values
            if op is ConditionOperator.NOT_IN:
                matched = not matched
            return _bool_result(matched)

        if op is ConditionOperator.INTERSECTS:
            if data_type is not AttributeDataType.STRING_SET:
                raise TypeError("INTERSECTS requires STRING_SET")
            if not isinstance(expected, (list, tuple, set, frozenset)):
                raise TypeError("INTERSECTS expects an array/set")
            expected_values = {str(item) for item in expected}
            return _bool_result(bool(set(actual) & expected_values))

        if op is ConditionOperator.CONTAINS:
            if isinstance(actual, str):
                if not isinstance(expected, str):
                    raise TypeError("string CONTAINS expects a string")
                return _bool_result(expected in actual)
            if isinstance(actual, tuple):
                return _bool_result(str(expected) in actual)
            raise TypeError("CONTAINS requires STRING or STRING_SET")

        expected_value = _coerce(expected, data_type)

        if op is ConditionOperator.EQ:
            return _bool_result(actual == expected_value)
        if op is ConditionOperator.NEQ:
            return _bool_result(actual != expected_value)
        if op is ConditionOperator.LT:
            return _bool_result(actual < expected_value)
        if op is ConditionOperator.LTE:
            return _bool_result(actual <= expected_value)
        if op is ConditionOperator.GT:
            return _bool_result(actual > expected_value)
        if op is ConditionOperator.GTE:
            return _bool_result(actual >= expected_value)

        raise ValueError(f"unsupported operator {op}")

    @staticmethod
    def _condition_result(
        condition: RuleCondition,
        result: ConditionResult,
        actual: Any,
        reason: str,
    ) -> ConditionEvaluation:
        return ConditionEvaluation(
            condition_id=condition.id,
            attribute_key=condition.attribute.key,
            result=result,
            blocking=condition.blocking,
            verification_status=condition.verification_status,
            actual_value=actual,
            expected_value=_jsonable(condition.expected_value),
            reason_code=reason,
        )

    @staticmethod
    def _public_status(
        rule_set: RuleSet,
        root: ConditionResult,
        condition_results: list[ConditionEvaluation],
    ) -> EligibilityStatus:
        blocking = [item for item in condition_results if item.blocking]

        if root is ConditionResult.ERROR or any(
            item.result is ConditionResult.ERROR for item in blocking
        ):
            return EligibilityStatus.NEEDS_REVIEW

        if root is ConditionResult.FAIL:
            failed = [
                item
                for item in blocking
                if item.result is ConditionResult.FAIL
            ]
            if any(
                item.verification_status is not VerificationStatus.VERIFIED
                for item in failed
            ):
                return EligibilityStatus.NEEDS_REVIEW
            return EligibilityStatus.INELIGIBLE

        if root is ConditionResult.UNKNOWN:
            return EligibilityStatus.NEEDS_INFORMATION

        if root is ConditionResult.NOT_APPLICABLE:
            return EligibilityStatus.NEEDS_REVIEW

        if root is ConditionResult.PASS:
            all_blocking_verified = all(
                item.verification_status is VerificationStatus.VERIFIED
                for item in blocking
                if item.result is not ConditionResult.NOT_APPLICABLE
            )
            if (
                rule_set.completeness_status is CompletenessStatus.COMPLETE
                and rule_set.verification_status is VerificationStatus.VERIFIED
                and all_blocking_verified
            ):
                return EligibilityStatus.ELIGIBLE
            return EligibilityStatus.LIKELY_ELIGIBLE

        return EligibilityStatus.NEEDS_REVIEW


def _and(results: list[ConditionResult]) -> ConditionResult:
    active = [r for r in results if r is not ConditionResult.NOT_APPLICABLE]
    if not active:
        return ConditionResult.NOT_APPLICABLE
    if ConditionResult.FAIL in active:
        return ConditionResult.FAIL
    if ConditionResult.ERROR in active:
        return ConditionResult.ERROR
    if ConditionResult.UNKNOWN in active:
        return ConditionResult.UNKNOWN
    return ConditionResult.PASS


def _or(results: list[ConditionResult]) -> ConditionResult:
    active = [r for r in results if r is not ConditionResult.NOT_APPLICABLE]
    if not active:
        return ConditionResult.NOT_APPLICABLE
    if ConditionResult.PASS in active:
        return ConditionResult.PASS
    if ConditionResult.ERROR in active:
        return ConditionResult.ERROR
    if ConditionResult.UNKNOWN in active:
        return ConditionResult.UNKNOWN
    return ConditionResult.FAIL


def _negate(result: ConditionResult) -> ConditionResult:
    if result is ConditionResult.PASS:
        return ConditionResult.FAIL
    if result is ConditionResult.FAIL:
        return ConditionResult.PASS
    return result


def _bool_result(value: bool) -> ConditionResult:
    return ConditionResult.PASS if value else ConditionResult.FAIL


def _coerce(value: Any, data_type: AttributeDataType) -> Any:
    if data_type in (
        AttributeDataType.STRING,
        AttributeDataType.ENUM,
        AttributeDataType.GEO_ID,
    ):
        if not isinstance(value, str):
            raise TypeError(f"{data_type.value} requires string")
        return value

    if data_type in (
        AttributeDataType.INTEGER,
        AttributeDataType.MONEY_MINOR,
        AttributeDataType.PERCENT_BPS,
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{data_type.value} requires integer")
        return value

    if data_type is AttributeDataType.NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("NUMBER requires int/float")
        return float(value)

    if data_type is AttributeDataType.BOOLEAN:
        if not isinstance(value, bool):
            raise TypeError("BOOLEAN requires bool")
        return value

    if data_type is AttributeDataType.STRING_SET:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise TypeError("STRING_SET requires a collection")
        if any(not isinstance(item, str) for item in value):
            raise TypeError("STRING_SET items must be strings")
        return tuple(sorted(set(value)))

    if data_type is AttributeDataType.DATE:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise TypeError("DATE requires ISO date/date")

    if data_type is AttributeDataType.DATETIME:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise TypeError("DATETIME requires ISO datetime/datetime")

    raise TypeError(f"unsupported attribute type {data_type}")


def _jsonable(value: Any) -> Any:
    if value is KNOWN_ABSENT:
        return {"$absent": True}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
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


def _snapshot_hash(values: dict[str, Any]) -> str:
    normalized = {
        key: _jsonable(value)
        for key, value in sorted(values.items())
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
