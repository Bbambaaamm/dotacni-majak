from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HistoricalAward:
    id: str
    project_title: str
    recipient_name: str
    currency_code: str
    source_url: str
    ontology_terms: tuple[str, ...] = ()
    project_description: str | None = None
    recipient_ico: str | None = None
    grant_amount_minor: int | None = None
    total_cost_minor: int | None = None
    decision_date: str | None = None
    award_year: int | None = None
    location_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("award id must not be empty")
        if not self.project_title:
            raise ValueError("project_title must not be empty")
        if not self.recipient_name:
            raise ValueError("recipient_name must not be empty")
        if len(self.currency_code) != 3 or not self.currency_code.isupper():
            raise ValueError("currency_code must be uppercase 3-letter code")
        if self.grant_amount_minor is not None and self.grant_amount_minor < 0:
            raise ValueError("grant_amount_minor must be >= 0")
        if self.total_cost_minor is not None and self.total_cost_minor < 0:
            raise ValueError("total_cost_minor must be >= 0")


@dataclass(frozen=True, slots=True)
class HistoricalSimilarityResult:
    award: HistoricalAward
    shared_ontology_terms: tuple[str, ...]
    ontology_overlap_ratio_ppm: int
    similarity_basis: str = "ONTOLOGY_OVERLAP"

    @property
    def is_historical_context(self) -> bool:
        return True


class HistoricalSimilarityService:
    """Finds similar *historical examples*, never approval probabilities.

    Ranking is based only on deterministic overlap between project ontology
    terms and ontology terms attached to historical awards. The returned ratio
    is a similarity signal, not a probability of obtaining support.
    """

    def find_similar(
        self,
        *,
        project_ontology_terms: tuple[str, ...] | list[str],
        awards: tuple[HistoricalAward, ...] | list[HistoricalAward],
        limit: int = 5,
    ) -> tuple[HistoricalSimilarityResult, ...]:
        if limit < 1:
            raise ValueError("limit must be >= 1")

        project_terms = {term for term in project_ontology_terms if term}
        if not project_terms:
            return ()

        results: list[HistoricalSimilarityResult] = []
        for award in awards:
            award_terms = set(award.ontology_terms)
            shared = tuple(sorted(project_terms.intersection(award_terms)))
            if not shared:
                continue

            # Ratio is intentionally normalized only to the user's project
            # concepts. It says "how much of this project's ontology is also
            # present in the historical example", not "chance of success".
            ratio_ppm = len(shared) * 1_000_000 // len(project_terms)
            results.append(
                HistoricalSimilarityResult(
                    award=award,
                    shared_ontology_terms=shared,
                    ontology_overlap_ratio_ppm=ratio_ppm,
                )
            )

        results.sort(
            key=lambda item: (
                -item.ontology_overlap_ratio_ppm,
                -(item.award.award_year or 0),
                item.award.project_title.casefold(),
                item.award.id,
            )
        )
        return tuple(results[:limit])
