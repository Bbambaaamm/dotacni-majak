import gzip
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "red-history" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "history" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "search" / "src"))

from dotacni_majak_red_history import RedHistoricalConnector
from dotacni_majak_search.ontology import OntologyIndex


FIXTURES = ROOT / "connectors" / "red-history" / "fixtures"
ONTOLOGY = ROOT / "data" / "ontology" / "v1"


def gz(name: str) -> bytes:
    return gzip.compress((FIXTURES / name).read_bytes())


class RedHistoricalConnectorTest(unittest.TestCase):
    def setUp(self):
        self.connector = RedHistoricalConnector(
            ontology=OntologyIndex.from_directory(ONTOLOGY)
        )

    def test_joins_recipient_grant_and_decisions(self):
        result = self.connector.from_compressed_csv(
            dotace_gzip=gz("dotace.csv"),
            prijemce_gzip=gz("prijemce.csv"),
            rozhodnuti_gzip=gz("rozhodnuti.csv"),
            snapshot_ids=("raw:dotace", "raw:prijemce", "raw:rozhodnuti"),
        )

        self.assertEqual(len(result.awards), 1)
        award = result.awards[0]
        self.assertEqual(award.id, "red:D1")
        self.assertEqual(award.recipient_name, "TJ Test")
        self.assertEqual(award.recipient_ico, "12345678")
        self.assertEqual(award.project_title, "Rekonstrukce tenisových kurtů")
        self.assertEqual(award.grant_amount_minor, 85_000_050)
        self.assertEqual(award.award_year, 2025)
        self.assertEqual(award.decision_date, "2025-07-15")
        self.assertIn("TENNIS", award.ontology_terms)
        self.assertIn("SPORT_INFRASTRUCTURE", award.ontology_terms)
        self.assertEqual(
            result.snapshot_ids,
            ("raw:dotace", "raw:prijemce", "raw:rozhodnuti"),
        )

    def test_returnable_aid_is_not_exposed_as_historical_grant(self):
        result = self.connector.from_compressed_csv(
            dotace_gzip=gz("dotace.csv"),
            prijemce_gzip=gz("prijemce.csv"),
            rozhodnuti_gzip=gz("rozhodnuti.csv"),
        )
        self.assertNotIn("red:D2", {award.id for award in result.awards})
        self.assertIn("D2:RETURNABLE_AID_ONLY", result.rejected)

    def test_missing_decision_keeps_amount_unknown(self):
        result = self.connector.from_rows(
            dotace=[
                {
                    "idDotace": "D3",
                    "idPrijemce": "P1",
                    "projektNazev": "Sportovní areál",
                }
            ],
            prijemce=[
                {
                    "idPrijemce": "P1",
                    "ico": "123",
                    "obchodniJmeno": "TJ",
                }
            ],
            rozhodnuti=[],
        )
        self.assertEqual(result.awards[0].grant_amount_minor, None)

    def test_sub_minor_precision_is_rejected(self):
        with self.assertRaises(ValueError):
            self.connector.from_rows(
                dotace=[
                    {
                        "idDotace": "D1",
                        "idPrijemce": "P1",
                        "projektNazev": "Test",
                    }
                ],
                prijemce=[
                    {
                        "idPrijemce": "P1",
                        "obchodniJmeno": "TJ",
                    }
                ],
                rozhodnuti=[
                    {
                        "idDotace": "D1",
                        "castkaRozhodnuta": "1.001",
                        "navratnostIndikator": "False",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
