import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "search" / "src"))

from dotacni_majak_search.semantic import (
    InMemoryCosineIndex,
    SearchProfile,
    SemanticSearchService,
    VectorBudgetExceeded,
    VectorBudgetLimits,
    VectorBudgetManager,
)


class MappingProvider:
    name = "test-mapping"
    dimensions = 3

    def __init__(self):
        self.mapping = {
            "sport": [1.0, 0.0, 0.0],
            "digital": [0.0, 1.0, 0.0],
        }

    async def embed(self, texts):
        result = []
        for text in texts:
            lowered = text.casefold()
            if "tenis" in lowered or "sport" in lowered:
                result.append(self.mapping["sport"])
            elif "digital" in lowered or "software" in lowered:
                result.append(self.mapping["digital"])
            else:
                result.append([0.0, 0.0, 1.0])
        return result


class SemanticSearchTest(unittest.IsolatedAsyncioTestCase):
    async def test_search_profile_is_compact_and_explainable(self):
        profile = SearchProfile(
            grant_call_version_id="v1",
            title="Regionální sportovní infrastruktura",
            purpose="Modernizace sportovních zařízení",
            supported_activities=("technické zhodnocení", "venkovní sportoviště"),
            ontology_terms=("SPORT_INFRASTRUCTURE", "TENNIS"),
        )
        rendered = profile.render()
        self.assertIn("Regionální sportovní infrastruktura", rendered)
        self.assertIn("SPORT_INFRASTRUCTURE", rendered)
        self.assertNotIn("None", rendered)

    async def test_tennis_query_prefers_sport_profile(self):
        provider = MappingProvider()
        index = InMemoryCosineIndex()
        service = SemanticSearchService(
            provider=provider,
            index=index,
            indexed_vector_count=0,
        )
        profiles = [
            SearchProfile(
                grant_call_version_id="sport-v1",
                title="Sportovní infrastruktura",
                supported_activities=("sportoviště", "modernizace"),
            ),
            SearchProfile(
                grant_call_version_id="digital-v1",
                title="Digitalizace podniků",
                supported_activities=("software", "digitalizace"),
            ),
        ]
        indexed = await service.embed_profiles(profiles)
        self.assertTrue(indexed.available)

        result = await service.search(
            "rekonstrukce tenisových kurtů",
            top_k=2,
        )
        self.assertTrue(result.available)
        self.assertEqual(result.hits[0].grant_call_version_id, "sport-v1")

    async def test_missing_semantic_backend_degrades_cleanly(self):
        service = SemanticSearchService(provider=None, index=None)
        result = await service.search("tenis")
        self.assertFalse(result.available)
        self.assertIn("unavailable", result.reason)

    async def test_budget_exhaustion_degrades_semantic_not_whole_search(self):
        provider = MappingProvider()
        index = InMemoryCosineIndex()
        budget = VectorBudgetManager(
            VectorBudgetLimits(
                max_stored_dimensions=3,
                max_queried_dimensions=3,
            )
        )
        service = SemanticSearchService(
            provider=provider,
            index=index,
            budget=budget,
        )
        first = await service.embed_profiles([
            SearchProfile(
                grant_call_version_id="sport-v1",
                title="Sport",
            )
        ])
        self.assertTrue(first.available)

        second = await service.embed_profiles([
            SearchProfile(
                grant_call_version_id="sport-v2",
                title="Sport 2",
            )
        ])
        self.assertFalse(second.available)
        self.assertIn("VectorBudgetExceeded", second.reason)

    def test_budget_math_is_explicit(self):
        budget = VectorBudgetManager(
            VectorBudgetLimits(
                max_stored_dimensions=6,
                max_queried_dimensions=12,
            )
        )
        budget.reserve_store(vector_count=2, dimensions=3)
        self.assertEqual(budget.usage.stored_dimensions, 6)
        budget.reserve_query(indexed_vector_count=2, dimensions=3)
        self.assertEqual(budget.usage.queried_dimensions, 9)
        with self.assertRaises(VectorBudgetExceeded):
            budget.reserve_query(indexed_vector_count=1, dimensions=3)


if __name__ == "__main__":
    unittest.main()
