import json
import unittest
from collections import defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "data" / "ontology" / "v1"


class OntologyV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.terms = json.loads((ONTOLOGY / "terms.json").read_text(encoding="utf-8"))
        cls.edges = json.loads((ONTOLOGY / "edges.json").read_text(encoding="utf-8"))
        cls.synonyms = json.loads((ONTOLOGY / "synonyms.json").read_text(encoding="utf-8"))

    def test_required_core_domains_exist(self):
        codes = {term["code"] for term in self.terms["terms"]}
        for code in {
            "SPORT", "ENERGY", "BUILDINGS", "EDUCATION", "SOCIAL",
            "CULTURE", "HERITAGE", "ENVIRONMENT", "WATER", "WASTE",
            "TRANSPORT", "DIGITALIZATION", "BUSINESS", "RESEARCH",
            "AGRICULTURE", "TOURISM", "HEALTH", "COMMUNITY",
            "HOUSING", "SECURITY", "PUBLIC_SPACE",
        }:
            self.assertIn(code, codes)

    def test_tennis_court_has_broader_path_to_sport_infrastructure(self):
        graph = defaultdict(list)
        for edge in self.edges["edges"]:
            if edge["relation"] == "BROADER":
                graph[edge["from"]].append(edge["to"])

        queue = deque(["TENNIS_COURT"])
        seen = {"TENNIS_COURT"}
        while queue:
            node = queue.popleft()
            for parent in graph[node]:
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)

        self.assertIn("OUTDOOR_SPORT_FACILITY", seen)
        self.assertIn("SPORT_FACILITY", seen)
        self.assertIn("SPORT_INFRASTRUCTURE", seen)
        self.assertIn("SPORT", seen)

    def test_reconstruction_connects_to_technical_improvement(self):
        relations = {
            (e["from"], e["to"], e["relation"])
            for e in self.edges["edges"]
        }
        self.assertIn(
            ("RECONSTRUCTION", "TECHNICAL_IMPROVEMENT", "RELATED"),
            relations,
        )

    def test_user_language_contains_tennis_and_reconstruction_forms(self):
        by_text = {s["text"].casefold(): s["term"] for s in self.synonyms["synonyms"]}
        self.assertEqual(by_text["tenisové kurty"], "TENNIS_COURT")
        self.assertEqual(by_text["rekonstruovat"], "RECONSTRUCTION")


if __name__ == "__main__":
    unittest.main()
