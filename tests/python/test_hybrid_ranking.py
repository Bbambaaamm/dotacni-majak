import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "search" / "src"))

from dotacni_majak_search.ranking import (
    HybridRanker,
    HybridSignals,
    MatchBand,
    MatchReasonCode,
    bm25_rank_to_relevance,
    ontology_overlap,
)


class HybridRankingTest(unittest.TestCase):
    def test_semantic_unavailable_reweights_remaining_signals(self):
        ranker = HybridRanker()
        with_semantic = ranker.rank([
            HybridSignals(
                "sport",
                lexical_relevance=0.8,
                ontology_relevance=0.8,
                semantic_relevance=0.8,
            )
        ])[0]
        without_semantic = ranker.rank([
            HybridSignals(
                "sport",
                lexical_relevance=0.8,
                ontology_relevance=0.8,
                semantic_relevance=None,
            )
        ])[0]
        self.assertAlmostEqual(with_semantic.relevance_score, 0.8)
        self.assertAlmostEqual(without_semantic.relevance_score, 0.8)

    def test_tennis_broader_ontology_can_rank_generic_sport_call_high(self):
        ranked = HybridRanker().rank([
            HybridSignals(
                "sport-infrastructure",
                lexical_relevance=0.45,
                ontology_relevance=1.0,
                semantic_relevance=0.90,
            ),
            HybridSignals(
                "digital",
                lexical_relevance=0.30,
                ontology_relevance=0.0,
                semantic_relevance=0.10,
            ),
        ])
        self.assertEqual(ranked[0].grant_call_version_id, "sport-infrastructure")
        self.assertEqual(ranked[0].match_band, MatchBand.VERY_GOOD)
        self.assertIn(MatchReasonCode.ONTOLOGY_MATCH, ranked[0].reasons)
        self.assertIn(MatchReasonCode.SEMANTIC_INTENT_MATCH, ranked[0].reasons)

    def test_raw_score_is_not_required_for_reason_explanation(self):
        hit = HybridRanker().rank([
            HybridSignals(
                "v1",
                lexical_relevance=0.9,
                ontology_relevance=0.8,
                semantic_relevance=None,
            )
        ])[0]
        self.assertEqual(hit.match_band, MatchBand.VERY_GOOD)
        self.assertIn(MatchReasonCode.STRONG_LEXICAL_MATCH, hit.reasons)
        self.assertIn(MatchReasonCode.ONTOLOGY_MATCH, hit.reasons)

    def test_bm25_transform_is_monotonic_and_bounded(self):
        weak = bm25_rank_to_relevance(-0.2)
        strong = bm25_rank_to_relevance(-3.0)
        self.assertGreater(strong, weak)
        self.assertGreaterEqual(weak, 0)
        self.assertLessEqual(strong, 1)

    def test_ontology_overlap_measures_query_coverage(self):
        self.assertEqual(
            ontology_overlap(
                ["SPORT", "SPORT_INFRASTRUCTURE", "TENNIS"],
                ["SPORT", "SPORT_INFRASTRUCTURE"],
            ),
            2 / 3,
        )
        self.assertEqual(ontology_overlap([], ["SPORT"]), 0.0)


if __name__ == "__main__":
    unittest.main()
