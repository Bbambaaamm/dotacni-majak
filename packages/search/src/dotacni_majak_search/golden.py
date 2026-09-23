from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RelevanceJudgment(str, Enum):
    RELEVANT = "relevant"
    PARTIALLY_RELEVANT = "partially_relevant"
    IRRELEVANT = "irrelevant"


@dataclass(frozen=True, slots=True)
class GoldenCandidate:
    candidate_id: str
    label: RelevanceJudgment
    ontology_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    query_id: str
    text: str
    expected_terms: tuple[str, ...]
    candidates: tuple[GoldenCandidate, ...]


def load_golden_dataset(path: str | Path) -> tuple[GoldenQuery, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != "1.0.0":
        raise ValueError("unsupported golden dataset version")

    queries: list[GoldenQuery] = []
    seen_ids: set[str] = set()
    for item in payload["queries"]:
        query_id = str(item["id"])
        if query_id in seen_ids:
            raise ValueError(f"duplicate golden query id: {query_id}")
        seen_ids.add(query_id)

        candidates = tuple(
            GoldenCandidate(
                candidate_id=str(candidate["id"]),
                label=RelevanceJudgment(candidate["label"]),
                ontology_terms=tuple(candidate["ontology_terms"]),
            )
            for candidate in item["candidates"]
        )
        if not candidates:
            raise ValueError(f"{query_id}: at least one candidate required")

        queries.append(
            GoldenQuery(
                query_id=query_id,
                text=str(item["query"]),
                expected_terms=tuple(item["expected_terms"]),
                candidates=candidates,
            )
        )

    return tuple(queries)
