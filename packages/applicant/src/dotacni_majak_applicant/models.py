from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True, slots=True)
class ResolvedFact:
    attribute_key: str
    value: Any
    source_kind: str
    source_reference: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ApplicantResolution:
    status: ResolutionStatus
    facts: tuple[ResolvedFact, ...] = ()
    warnings: tuple[str, ...] = ()

    def fact_map(self) -> dict[str, Any]:
        return {fact.attribute_key: fact.value for fact in self.facts}


@dataclass(frozen=True, slots=True)
class MunicipalityPopulation:
    municipality_code: str
    population: int
    as_of: date
    source_reference: str
    observed_at: datetime


class MunicipalityPopulationResolver(Protocol):
    async def resolve(
        self,
        municipality_code: str,
    ) -> MunicipalityPopulation | None: ...


class InMemoryMunicipalityPopulationResolver:
    def __init__(
        self,
        records: dict[str, MunicipalityPopulation],
    ) -> None:
        self.records = dict(records)

    async def resolve(
        self,
        municipality_code: str,
    ) -> MunicipalityPopulation | None:
        return self.records.get(municipality_code)
