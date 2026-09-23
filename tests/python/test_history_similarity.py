import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "history" / "src"))

from dotacni_majak_history import (
    HistoricalAward,
    HistoricalSimilarityService,
)


class HistoricalSimilarityServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = HistoricalSimilarityService()

    def test_returns_only_historical_examples_with_shared_ontology(self):
        awards = [
            HistoricalAward(
                id="tennis-2025",
                project_title="Obnova tenisových kurtů",
                recipient_name="TJ Example",
                currency_code="CZK",
                source_url="https://example.gov.cz/award/1",
                award_year=2025,
                ontology_terms=("SPORT", "SPORT_INFRASTRUCTURE", "TENNIS"),
            ),
            HistoricalAward(
                id="school-2025",
                project_title="Modernizace školy",
                recipient_name="Obec Example",
                currency_code="CZK",
                source_url="https://example.gov.cz/award/2",
                award_year=2025,
                ontology_terms=("EDUCATION", "BUILDINGS"),
            ),
        ]

        result = self.service.find_similar(
            project_ontology_terms=("SPORT_INFRASTRUCTURE", "TENNIS"),
            awards=awards,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].award.id, "tennis-2025")
        self.assertTrue(result[0].is_historical_context)
        self.assertEqual(
            result[0].shared_ontology_terms,
            ("SPORT_INFRASTRUCTURE", "TENNIS"),
        )
        self.assertEqual(result[0].ontology_overlap_ratio_ppm, 1_000_000)
        self.assertFalse(hasattr(result[0], "success_probability"))

    def test_more_recent_breaks_equal_similarity_tie(self):
        awards = [
            HistoricalAward(
                id="old",
                project_title="Sportoviště A",
                recipient_name="A",
                currency_code="CZK",
                source_url="https://example.gov.cz/old",
                award_year=2022,
                ontology_terms=("SPORT_INFRASTRUCTURE",),
            ),
            HistoricalAward(
                id="new",
                project_title="Sportoviště B",
                recipient_name="B",
                currency_code="CZK",
                source_url="https://example.gov.cz/new",
                award_year=2025,
                ontology_terms=("SPORT_INFRASTRUCTURE",),
            ),
        ]

        result = self.service.find_similar(
            project_ontology_terms=("SPORT_INFRASTRUCTURE",),
            awards=awards,
        )
        self.assertEqual([item.award.id for item in result], ["new", "old"])

    def test_empty_project_ontology_returns_no_examples(self):
        result = self.service.find_similar(
            project_ontology_terms=(),
            awards=[],
        )
        self.assertEqual(result, ())

    def test_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            self.service.find_similar(
                project_ontology_terms=("SPORT",),
                awards=[],
                limit=0,
            )


if __name__ == "__main__":
    unittest.main()
