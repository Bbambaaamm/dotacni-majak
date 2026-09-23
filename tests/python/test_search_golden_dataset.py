import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "search" / "src"))

from dotacni_majak_search import HybridRanker, HybridSignals
from dotacni_majak_search.golden import (
    RelevanceJudgment,
    load_golden_dataset,
)
from dotacni_majak_search.ontology import OntologyIndex


class GoldenSearchDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ontology = OntologyIndex.from_directory(
            ROOT / "data" / "ontology" / "v1"
        )
        cls.queries = load_golden_dataset(
            ROOT / "data" / "golden" / "search-v1.json"
        )

    def test_dataset_has_required_size_and_all_labels(self):
        self.assertGreaterEqual(len(self.queries), 10)
        labels = {
            candidate.label
            for query in self.queries
            for candidate in query.candidates
        }
        self.assertEqual(
            labels,
            {
                RelevanceJudgment.RELEVANT,
                RelevanceJudgment.PARTIALLY_RELEVANT,
                RelevanceJudgment.IRRELEVANT,
            },
        )

    def test_every_query_resolves_expected_ontology_terms(self):
        for query in self.queries:
            with self.subTest(query=query.query_id):
                resolved = self.ontology.resolve(query.text)
                missing = set(query.expected_terms) - set(resolved)
                self.assertEqual(
                    missing,
                    set(),
                    f"{query.query_id} missing terms {sorted(missing)}",
                )

    def test_every_relevant_candidate_has_more_ontology_overlap_than_irrelevant(self):
        for query in self.queries:
            with self.subTest(query=query.query_id):
                resolved = self.ontology.resolve(query.text)
                by_label = {
                    candidate.label: self.ontology.score_terms(
                        resolved,
                        candidate.ontology_terms,
                    )
                    for candidate in query.candidates
                }
                self.assertGreater(
                    by_label[RelevanceJudgment.RELEVANT],
                    by_label[RelevanceJudgment.IRRELEVANT],
                )

    def test_tennis_query_reaches_generic_sport_infrastructure(self):
        query = next(
            item for item in self.queries
            if item.query_id == "tennis-court-reconstruction"
        )
        resolved = self.ontology.resolve(query.text)
        self.assertIn("TENNIS_COURT", resolved)
        self.assertIn("OUTDOOR_SPORT_FACILITY", resolved)
        self.assertIn("SPORT_FACILITY", resolved)
        self.assertIn("SPORT_INFRASTRUCTURE", resolved)
        self.assertIn("RECONSTRUCTION", resolved)
        self.assertIn("TECHNICAL_IMPROVEMENT", resolved)

        candidates = []
        for candidate in query.candidates:
            candidates.append(
                HybridSignals(
                    grant_call_version_id=candidate.candidate_id,
                    lexical_relevance=0.0,
                    ontology_relevance=self.ontology.score_terms(
                        resolved,
                        candidate.ontology_terms,
                    ),
                    semantic_relevance=None,
                )
            )

        ranked = HybridRanker().rank(candidates)
        positions = {
            result.grant_call_version_id: index
            for index, result in enumerate(ranked)
        }
        self.assertLess(
            positions["generic-sport-infrastructure"],
            positions["business-digitalisation"],
        )


if __name__ == "__main__":
    unittest.main()
