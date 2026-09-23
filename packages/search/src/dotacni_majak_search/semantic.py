from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class SearchProfile:
    grant_call_version_id: str
    title: str
    purpose: str = ""
    supported_activities: tuple[str, ...] = ()
    applicant_summary: str = ""
    eligible_cost_summary: str = ""
    ontology_terms: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

    def render(self) -> str:
        parts = [
            ("title", self.title),
            ("purpose", self.purpose),
            ("supported activities", "; ".join(self.supported_activities)),
            ("applicants", self.applicant_summary),
            ("eligible costs", self.eligible_cost_summary),
            ("ontology", "; ".join(self.ontology_terms)),
            ("keywords", "; ".join(self.keywords)),
        ]
        return "\n".join(
            f"{label}: {value.strip()}"
            for label, value in parts
            if value and value.strip()
        )


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class SemanticVector:
    vector_id: str
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SemanticHit:
    grant_call_version_id: str
    score: float


class SemanticIndex(Protocol):
    async def upsert(self, vectors: Sequence[SemanticVector]) -> None: ...

    async def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
    ) -> list[SemanticHit]: ...


@dataclass(frozen=True, slots=True)
class VectorBudgetLimits:
    max_stored_dimensions: int
    max_queried_dimensions: int

    def __post_init__(self) -> None:
        if self.max_stored_dimensions < 0 or self.max_queried_dimensions < 0:
            raise ValueError("vector budget limits must be >= 0")


@dataclass(slots=True)
class VectorBudgetUsage:
    stored_dimensions: int = 0
    queried_dimensions: int = 0


class VectorBudgetExceeded(RuntimeError):
    pass


class VectorBudgetManager:
    """Provider-agnostic vector usage guard.

    Limits are explicit configuration, never assumed from a provider plan.
    This is intentional because provider free-tier availability may change.
    """

    def __init__(
        self,
        limits: VectorBudgetLimits,
        usage: VectorBudgetUsage | None = None,
    ) -> None:
        self.limits = limits
        self.usage = usage or VectorBudgetUsage()

    def reserve_store(
        self,
        *,
        vector_count: int,
        dimensions: int,
        replacing_vector_count: int = 0,
    ) -> None:
        if min(vector_count, dimensions, replacing_vector_count) < 0:
            raise ValueError("vector counts and dimensions must be >= 0")
        delta = (vector_count - replacing_vector_count) * dimensions
        projected = self.usage.stored_dimensions + delta
        if projected < 0:
            raise ValueError("stored dimensions cannot become negative")
        if projected > self.limits.max_stored_dimensions:
            raise VectorBudgetExceeded(
                f"stored vector dimensions would be {projected}, "
                f"limit is {self.limits.max_stored_dimensions}"
            )
        self.usage.stored_dimensions = projected

    def reserve_query(
        self,
        *,
        indexed_vector_count: int,
        dimensions: int,
    ) -> None:
        if indexed_vector_count < 0 or dimensions < 0:
            raise ValueError("indexed_vector_count/dimensions must be >= 0")
        # Vector providers may meter both query vector and examined index vectors.
        # We deliberately budget the conservative (N + 1) * dimensions shape.
        delta = (indexed_vector_count + 1) * dimensions
        projected = self.usage.queried_dimensions + delta
        if projected > self.limits.max_queried_dimensions:
            raise VectorBudgetExceeded(
                f"queried vector dimensions would be {projected}, "
                f"limit is {self.limits.max_queried_dimensions}"
            )
        self.usage.queried_dimensions = projected


class InMemoryCosineIndex:
    """Reference semantic index for tests/local development."""

    def __init__(self) -> None:
        self._vectors: dict[str, tuple[float, ...]] = {}

    async def upsert(self, vectors: Sequence[SemanticVector]) -> None:
        for vector in vectors:
            self._vectors[vector.vector_id] = vector.values

    async def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
    ) -> list[SemanticHit]:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        query_values = tuple(float(x) for x in vector)
        scored = [
            SemanticHit(vector_id, _cosine(query_values, values))
            for vector_id, values in self._vectors.items()
        ]
        return sorted(
            scored,
            key=lambda hit: (-hit.score, hit.grant_call_version_id),
        )[:top_k]

    @property
    def vector_count(self) -> int:
        return len(self._vectors)


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    available: bool
    hits: tuple[SemanticHit, ...] = ()
    reason: str | None = None


class SemanticSearchService:
    """Optional semantic layer.

    Any provider/index/budget failure becomes an explicit unavailable result.
    Callers must continue with lexical + ontology + structured retrieval.
    """

    def __init__(
        self,
        *,
        provider: EmbeddingProvider | None,
        index: SemanticIndex | None,
        budget: VectorBudgetManager | None = None,
        indexed_vector_count: int = 0,
    ) -> None:
        self.provider = provider
        self.index = index
        self.budget = budget
        self.indexed_vector_count = indexed_vector_count

    async def embed_profiles(
        self,
        profiles: Sequence[SearchProfile],
    ) -> SemanticSearchResult:
        if self.provider is None or self.index is None:
            return SemanticSearchResult(False, reason="semantic provider unavailable")

        if not profiles:
            return SemanticSearchResult(True)

        try:
            if self.budget is not None:
                self.budget.reserve_store(
                    vector_count=len(profiles),
                    dimensions=self.provider.dimensions,
                )
            values = await self.provider.embed([p.render() for p in profiles])
            if len(values) != len(profiles):
                raise ValueError("embedding provider returned unexpected batch size")
            vectors = [
                SemanticVector(profile.grant_call_version_id, tuple(vector))
                for profile, vector in zip(profiles, values, strict=True)
            ]
            self._validate_dimensions(vectors)
            await self.index.upsert(vectors)
            self.indexed_vector_count += len(profiles)
            return SemanticSearchResult(True)
        except Exception as exc:
            return SemanticSearchResult(
                False,
                reason=f"{type(exc).__name__}: {exc}",
            )

    async def search(
        self,
        text: str,
        *,
        top_k: int = 20,
    ) -> SemanticSearchResult:
        if self.provider is None or self.index is None:
            return SemanticSearchResult(False, reason="semantic provider unavailable")
        if not text.strip():
            return SemanticSearchResult(True)

        try:
            if self.budget is not None:
                self.budget.reserve_query(
                    indexed_vector_count=self.indexed_vector_count,
                    dimensions=self.provider.dimensions,
                )
            batch = await self.provider.embed([text])
            if len(batch) != 1:
                raise ValueError("embedding provider returned unexpected query batch")
            vector = batch[0]
            if len(vector) != self.provider.dimensions:
                raise ValueError("embedding dimension mismatch")
            hits = await self.index.query(vector, top_k=top_k)
            return SemanticSearchResult(True, tuple(hits))
        except Exception as exc:
            return SemanticSearchResult(
                False,
                reason=f"{type(exc).__name__}: {exc}",
            )

    def _validate_dimensions(self, vectors: Sequence[SemanticVector]) -> None:
        expected = self.provider.dimensions if self.provider else None
        for vector in vectors:
            if len(vector.values) != expected:
                raise ValueError(
                    f"embedding dimension mismatch for {vector.vector_id}: "
                    f"{len(vector.values)} != {expected}"
                )


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vectors must have equal dimensions")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
