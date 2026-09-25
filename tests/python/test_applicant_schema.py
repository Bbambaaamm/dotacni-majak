import json
import unittest
from pathlib import Path


class ApplicantCanonicalSchemaTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def schema(self, name):
        return json.loads(
            (self.root / "schemas" / "v1" / name).read_text(encoding="utf-8")
        )

    def fixture(self, name):
        return json.loads(
            (self.root / "tests" / "fixtures" / "canonical" / name).read_text(
                encoding="utf-8"
            )
        )

    def test_applicant_type_supports_hierarchy(self):
        schema = self.schema("applicant-type.schema.json")
        self.assertIn("parentId", schema["properties"])
        self.assertEqual(
            schema["properties"]["code"]["pattern"],
            "^[A-Z][A-Z0-9_]*$",
        )

    def test_profile_is_backward_compatible_and_hierarchy_ready(self):
        schema = self.schema("applicant-profile.schema.json")
        self.assertIn("applicantType", schema["required"])
        self.assertNotIn("applicantTypeId", schema["required"])
        for key in {
            "applicantTypeId",
            "seatGeographyId",
            "publicPrivateStatus",
            "nonprofitStatus",
            "czNaceCodes",
            "fieldSources",
        }:
            self.assertIn(key, schema["properties"])

    def test_field_sources_include_official_resolvers_and_verification(self):
        source = self.schema("applicant-profile.schema.json")["$defs"]["fieldSource"]
        source_kinds = set(source["properties"]["sourceKind"]["enum"])
        self.assertTrue({"USER", "ARES", "CZSO", "OTHER_OFFICIAL"}.issubset(source_kinds))
        self.assertIn("verificationStatus", source["required"])

    def test_dynamic_attribute_value_preserves_type_and_provenance(self):
        schema = self.schema("applicant-attribute-value.schema.json")
        for key in {
            "valueType",
            "value",
            "sourceKind",
            "observedAt",
            "verificationStatus",
        }:
            self.assertIn(key, schema["required"])
        self.assertTrue(schema["allOf"])

    def test_reference_fixtures_cover_resolver_and_user_sources(self):
        applicant_type = self.fixture("applicant-type.json")
        profile = self.fixture("applicant-profile.json")
        attribute = self.fixture("applicant-attribute-value.json")

        self.assertEqual(applicant_type["parentId"], "applicant-type:nonprofit")
        self.assertEqual(profile["applicantType"], "SPORTS_CLUB")
        self.assertEqual(profile["applicantTypeId"], "applicant-type:sports-club")
        self.assertEqual(profile["fieldSources"]["ico"]["sourceKind"], "ARES")
        self.assertEqual(
            profile["fieldSources"]["municipalityPopulation"]["sourceKind"],
            "CZSO",
        )
        self.assertEqual(attribute["sourceKind"], "USER")
        self.assertEqual(attribute["verificationStatus"], "USER_DECLARED")


if __name__ == "__main__":
    unittest.main()
