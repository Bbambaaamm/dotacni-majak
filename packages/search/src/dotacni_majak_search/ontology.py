from __future__ import annotations

import json
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", without_marks)
    return _SPACE_RE.sub(" ", normalized).strip()


@dataclass(frozen=True, slots=True)
class OntologyMatch:
    term: str
    score: float
    source: str
    matched_text: str | None = None


@dataclass(frozen=True, slots=True)
class _Phrase:
    term: str
    normalized: str
    weight: float
    source: str


class OntologyIndex:
    """Small deterministic runtime matcher over versioned ontology data.

    This intentionally avoids LLM/NLP dependencies. It recognizes curated
    Czech phrases and expands only along explicit ontology edges.
    """

    def __init__(
        self,
        *,
        term_names: dict[str, str],
        synonyms: list[dict],
        edges: list[dict],
    ) -> None:
        self.term_names = dict(term_names)
        self._phrases: list[_Phrase] = []
        self._edges: dict[str, list[tuple[str, str, float]]] = {}

        for term, name in self.term_names.items():
            normalized = normalize_text(name)
            if normalized:
                self._phrases.append(
                    _Phrase(term, normalized, 1.0, "CANONICAL_NAME")
                )

        for item in synonyms:
            normalized = normalize_text(str(item["text"]))
            if not normalized:
                continue
            self._phrases.append(
                _Phrase(
                    str(item["term"]),
                    normalized,
                    float(item.get("weight", 1.0)),
                    f"SYNONYM:{item.get('type', 'UNKNOWN')}",
                )
            )

        # Match longer phrases first; if both a broad and precise phrase occur,
        # both terms remain available but the precise term is never hidden.
        self._phrases.sort(
            key=lambda phrase: (-len(phrase.normalized.split()), -len(phrase.normalized))
        )

        for edge in edges:
            source = str(edge["from"])
            target = str(edge["to"])
            relation = str(edge["relation"])
            weight = float(edge.get("weight", 1.0))
            self._edges.setdefault(source, []).append(
                (target, relation, weight)
            )

    @classmethod
    def from_directory(cls, directory: str | Path) -> "OntologyIndex":
        root = Path(directory)
        terms_payload = json.loads(
            (root / "terms.json").read_text(encoding="utf-8")
        )
        synonyms_payload = json.loads(
            (root / "synonyms.json").read_text(encoding="utf-8")
        )
        edges_payload = json.loads(
            (root / "edges.json").read_text(encoding="utf-8")
        )
        term_names = {
            str(item["code"]): str(item["name"])
            for item in terms_payload["terms"]
            if item.get("active", True)
        }
        return cls(
            term_names=term_names,
            synonyms=list(synonyms_payload["synonyms"]),
            edges=list(edges_payload["edges"]),
        )

    def match(self, text: str) -> dict[str, OntologyMatch]:
        normalized = normalize_text(text)
        if not normalized:
            return {}

        padded = f" {normalized} "
        matches: dict[str, OntologyMatch] = {}

        for phrase in self._phrases:
            needle = f" {phrase.normalized} "
            if needle not in padded:
                continue
            current = matches.get(phrase.term)
            candidate = OntologyMatch(
                term=phrase.term,
                score=phrase.weight,
                source=phrase.source,
                matched_text=phrase.normalized,
            )
            if current is None or candidate.score > current.score:
                matches[phrase.term] = candidate

        return matches

    def expand(
        self,
        direct_matches: dict[str, OntologyMatch] | Iterable[str],
        *,
        max_depth: int = 4,
        min_score: float = 0.35,
        allowed_relations: frozenset[str] = frozenset(
            {"BROADER", "RELATED", "PART_OF"}
        ),
    ) -> dict[str, OntologyMatch]:
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if not 0 <= min_score <= 1:
            raise ValueError("min_score must be between 0 and 1")

        if isinstance(direct_matches, dict):
            result = dict(direct_matches)
        else:
            result = {
                term: OntologyMatch(term, 1.0, "DIRECT_TERM")
                for term in direct_matches
            }

        queue = deque(
            (term, match.score, 0)
            for term, match in result.items()
        )

        while queue:
            source, source_score, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for target, relation, edge_weight in self._edges.get(source, []):
                if relation not in allowed_relations:
                    continue
                # Mild per-hop decay prevents very broad concepts from
                # outweighing a direct phrase while preserving reachability.
                score = source_score * edge_weight * 0.95
                if score < min_score:
                    continue
                previous = result.get(target)
                if previous is not None and previous.score >= score:
                    continue
                result[target] = OntologyMatch(
                    term=target,
                    score=score,
                    source=f"{relation}:{source}",
                )
                queue.append((target, score, depth + 1))

        return result

    def resolve(self, text: str, **expand_kwargs) -> dict[str, OntologyMatch]:
        return self.expand(self.match(text), **expand_kwargs)

    def score_terms(
        self,
        resolved_query: dict[str, OntologyMatch],
        grant_terms: Iterable[str],
    ) -> float:
        grant = set(grant_terms)
        if not resolved_query or not grant:
            return 0.0
        total = sum(match.score for match in resolved_query.values())
        if total <= 0:
            return 0.0
        matched = sum(
            match.score
            for term, match in resolved_query.items()
            if term in grant
        )
        return min(1.0, matched / total)
