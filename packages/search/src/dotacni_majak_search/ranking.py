from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class MatchBand(str, Enum):
    VERY_GOOD = "VERY_GOOD"
    POSSIBLE = "POSSIBLE"
    WEAK = "WEAK"


class MatchReasonCode(str, Enum):
    STRONG_LEXICAL_MATCH = "STRONG_LEXICAL_MATCH"
    SEMANTIC_INTENT_MATCH = "SEMANTIC_INTENT_MATCH"
    ONTOLOGY_MATCH = "ONTOLOGY_MATCH"


@dataclass(frozen=True, slots=True)
class HybridSignals:
    grant_call_version_id: str
    lexical_relevance: float = 0.0
    ontology_relevance: float = 0.0
    semantic_relevance: float | None = None

    def __post_init__(self) -> None:
        for name in ("lexical_relevance", "ontology_relevance"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.semantic_relevance is not None and not 0.0 <= self.semantic_relevance <= 1.0:
            raise ValueError("semantic_relevance must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class HybridWeights:
    lexical: float = 0.45
    ontology: float = 0.35
    semantic: float = 0.20

    def __post_init__(self) -> None:
        if min(self.lexical, self.ontology, self.semantic) < 0:
            raise ValueError("weights must be >= 0")
        if self.lexical + self.ontology + self.semantic <= 0:
            raise ValueError("at least one weight must be > 0")


@dataclass(frozen=True, slots=True)
class RankedGrantMatch:
    grant_call_version_id: str
    relevance_score: float
    match_band: MatchBand
    reasons: tuple[MatchReasonCode, ...]


class HybridRanker:
    """Combines retrieval signals into an internal relevance ranking.

    The score is NOT eligibility and NOT probability of receiving a grant.
    Public UI should normally expose match_band + reasons rather than the raw
    numerical score.
    """

    def __init__(
        self,
        weights: HybridWeights | None = None,
        *,
        very_good_threshold: float = 0.70,
        possible_threshold: float = 0.35,
    ) -> None:
        self.weights = weights or HybridWeights()
        if not 0 <= possible_threshold <= very_good_threshold <= 1:
            raise ValueError("invalid match-band thresholds")
        self.very_good_threshold = very_good_threshold
        self.possible_threshold = possible_threshold

    def rank(self, candidates: Iterable[HybridSignals]) -> list[RankedGrantMatch]:
        ranked = [self._rank_one(candidate) for candidate in candidates]
        return sorted(
            ranked,
            key=lambda item: (-item.relevance_score, item.grant_call_version_id),
        )

    def _rank_one(self, signals: HybridSignals) -> RankedGrantMatch:
        components: list[tuple[float, float]] = [
            (self.weights.lexical, signals.lexical_relevance),
            (self.weights.ontology, signals.ontology_relevance),
        ]
        if signals.semantic_relevance is not None:
            components.append((self.weights.semantic, signals.semantic_relevance))

        weight_sum = sum(weight for weight, _ in components)
        score = (
            sum(weight * value for weight, value in components) / weight_sum
            if weight_sum
            else 0.0
        )
        score = min(1.0, max(0.0, score))

        reasons: list[MatchReasonCode] = []
        if signals.lexical_relevance >= 0.55:
            reasons.append(MatchReasonCode.STRONG_LEXICAL_MATCH)
        if signals.ontology_relevance >= 0.50:
            reasons.append(MatchReasonCode.ONTOLOGY_MATCH)
        if (
            signals.semantic_relevance is not None
            and signals.semantic_relevance >= 0.65
        ):
            reasons.append(MatchReasonCode.SEMANTIC_INTENT_MATCH)

        if score >= self.very_good_threshold:
            band = MatchBand.VERY_GOOD
        elif score >= self.possible_threshold:
            band = MatchBand.POSSIBLE
        else:
            band = MatchBand.WEAK

        return RankedGrantMatch(
            grant_call_version_id=signals.grant_call_version_id,
            relevance_score=score,
            match_band=band,
            reasons=tuple(reasons),
        )


def bm25_rank_to_relevance(rank: float) -> float:
    """Convert SQLite FTS5 bm25 rank into bounded retrieval relevance.

    FTS5 bm25 uses smaller (typically more negative) values for stronger
    matches. This monotonic transformation is only used as a retrieval signal,
    not as a calibrated probability.
    """

    strength = max(0.0, -float(rank))
    return strength / (1.0 + strength)


def ontology_overlap(
    query_terms: Iterable[str],
    grant_terms: Iterable[str],
) -> float:
    query = {term for term in query_terms if term}
    grant = {term for term in grant_terms if term}
    if not query or not grant:
        return 0.0
    intersection = len(query & grant)
    return intersection / len(query)
