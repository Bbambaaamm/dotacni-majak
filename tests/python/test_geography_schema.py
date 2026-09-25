import json
import unittest
from pathlib import Path


class GeographyCanonicalSchemaTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def load_schema(self, name):
        return json.loads(
            (self.root / "schemas" / "v1" / name).read_text(encoding="utf-8")
        )

    def load_fixture(self, name):
        return json.loads(
            (self.root / "tests" / "fixtures" / "canonical" / name).read_text(
                encoding="utf-8"
            )
        )

    def test_geography_schema_covers_required_czech_levels_and_codes(self):
        schema = self.load_schema("geography.schema.json")
        geo_types = set(schema["properties"]["geographyType"]["enum"])
        self.assertTrue(
            {"COUNTRY", "NUTS2", "NUTS3", "REGION", "DISTRICT", "ORP", "MUNICIPALITY", "MAS"}
            .issubset(geo_types)
        )
        for key in {"parentId", "nutsCode", "lauCode", "orpCode", "masCode", "validFrom", "validTo"}:
            self.assertIn(key, schema["properties"])

    def test_grant_geography_has_explicit_include_exclude_and_scope(self):
        schema = self.load_schema("grant-geography.schema.json")
        self.assertEqual(
            set(schema["properties"]["mode"]["enum"]),
            {"INCLUDE", "EXCLUDE"},
        )
        self.assertEqual(
            set(schema["properties"]["appliesTo"]["enum"]),
            {"PROJECT_LOCATION", "APPLICANT_SEAT", "BOTH"},
        )
        self.assertIn("includeDescendants", schema["properties"])
        self.assertIn("evidenceId", schema["properties"])

    def test_reference_fixtures_match_contract_shape(self):
        geography = self.load_fixture("geography.json")
        grant_geography = self.load_fixture("grant-geography.json")

        self.assertEqual(geography["schemaVersion"], "1.0.0")
        self.assertEqual(geography["countryCode"], "CZ")
        self.assertEqual(geography["nutsCode"], "CZ032")
        self.assertEqual(grant_geography["mode"], "INCLUDE")
        self.assertEqual(grant_geography["appliesTo"], "PROJECT_LOCATION")
        self.assertTrue(grant_geography["includeDescendants"])


if __name__ == "__main__":
    unittest.main()
