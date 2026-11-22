import json
import unittest
from pathlib import Path


class ProjectIndicatorSchemaTest(unittest.TestCase):
    """Dedicated contract tests for the ProjectIndicator canonical schema.

    Project indicators are structured, code/name/unit metrics published by a
    funding source for a GrantCallVersion. They are immutable per version and
    carry the same provenance / necessity / completeness contract as
    grant_requirements and grant_evaluation_criteria — never converted into
    custom "chances" or probability estimates.
    """

    def setUp(self):
        self.schema_dir = Path(__file__).resolve().parents[2] / "schemas" / "v1"
        self.fixture_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "canonical"

    def load_schema(self, name):
        return json.loads((self.schema_dir / name).read_text(encoding="utf-8"))

    def load_fixture(self, name):
        return json.loads((self.fixture_dir / name).read_text(encoding="utf-8"))

    def test_schema_exists_and_is_closed_versioned(self):
        schema = self.load_schema("project-indicator.schema.json")
        self.assertEqual(schema["title"], "ProjectIndicator")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["schemaVersion"]["const"], "1.0.0"
        )
        self.assertIn("schemaVersion", schema["required"])

    def test_required_fields_cover_identity_provenance(self):
        schema = self.load_schema("project-indicator.schema.json")
        required = set(schema["required"])
        for field in (
            "schemaVersion", "id", "grantCallVersionId",
            "indicatorCode", "indicatorName", "necessity",
            "evidenceId", "completenessStatus", "verificationStatus",
            "sortOrder",
        ):
            self.assertIn(field, required, field)

    def test_indicator_code_is_required_string(self):
        schema = self.load_schema("project-indicator.schema.json")
        code = schema["properties"]["indicatorCode"]
        self.assertEqual(code["type"], "string")
        self.assertEqual(code.get("minLength"), 1)

    def test_indicator_name_is_required_string(self):
        schema = self.load_schema("project-indicator.schema.json")
        name = schema["properties"]["indicatorName"]
        self.assertEqual(name["type"], "string")
        self.assertEqual(name.get("minLength"), 1)

    def test_indicator_unit_is_nullable(self):
        schema = self.load_schema("project-indicator.schema.json")
        unit = schema["properties"]["indicatorUnit"]
        self.assertIn("null", json.dumps(unit))

    def test_indicator_category_is_optional_enum(self):
        schema = self.load_schema("project-indicator.schema.json")
        cat = schema["properties"]["indicatorCategory"]
        self.assertIn("null", json.dumps(cat))
        self.assertEqual(
            set(cat["enum"]),
            {"ENVIRONMENTAL", "ECONOMIC", "SOCIAL", "DIGITAL", "OTHER"},
        )

    def test_necessity_preserves_conditional_semantics(self):
        schema = self.load_schema("project-indicator.schema.json")
        self.assertEqual(
            set(schema["properties"]["necessity"]["enum"]),
            {"REQUIRED", "CONDITIONAL", "RECOMMENDED"},
        )
        self.assertIn("conditionGroupId", schema["properties"])

    def test_target_fields_are_nullable_when_not_published(self):
        schema = self.load_schema("project-indicator.schema.json")
        for field in ("baseline", "targetValue", "targetDirection", "targetPeriodType"):
            prop = schema["properties"][field]
            self.assertIn("null", json.dumps(prop), field)

    def test_target_direction_enum(self):
        schema = self.load_schema("project-indicator.schema.json")
        self.assertEqual(
            set(schema["properties"]["targetDirection"]["enum"]),
            {"INCREASE", "DECREASE", "REACH", "MAINTAIN"},
        )

    def test_target_period_type_enum(self):
        schema = self.load_schema("project-indicator.schema.json")
        self.assertEqual(
            set(schema["properties"]["targetPeriodType"]["enum"]),
            {"PER_PROJECT", "PER_YEAR", "PER_MONTH", "ONCE"},
        )

    def test_evidence_id_links_provenance(self):
        schema = self.load_schema("project-indicator.schema.json")
        evidence = schema["properties"]["evidenceId"]
        self.assertIn("null", json.dumps(evidence))
        self.assertEqual(evidence.get("minLength"), 1)

    def test_completeness_status_enum(self):
        schema = self.load_schema("project-indicator.schema.json")
        self.assertEqual(
            set(schema["properties"]["completenessStatus"]["enum"]),
            {"COMPLETE", "PARTIAL", "UNKNOWN"},
        )

    def test_verification_status_enum(self):
        schema = self.load_schema("project-indicator.schema.json")
        self.assertEqual(
            set(schema["properties"]["verificationStatus"]["enum"]),
            {
                "AUTO_EXTRACTED",
                "PARTIALLY_VERIFIED",
                "VERIFIED",
                "NEEDS_REVIEW",
            },
        )

    def test_no_chance_or_probability_fields(self):
        """Acceptance: explicit indicators must NOT become custom chances."""
        schema = self.load_schema("project-indicator.schema.json")
        forbidden = {
            "probability", "chance", "likelihood", "score",
            "matchScore", "successRate", "confidenceScore", "odds",
        }
        self.assertFalse(
            forbidden & set(schema["properties"].keys()),
            f"schema must not contain chance/probability fields: "
            f"{forbidden & set(schema['properties'].keys())}",
        )

    def test_fixture_matches_contract(self):
        fixture = self.load_fixture("project-indicator.json")
        self.assertEqual(fixture["schemaVersion"], "1.0.0")

    def test_fixture_has_evidence_or_unknown(self):
        """Acceptance: every critical claim has evidence/UNKNOWN."""
        fixture = self.load_fixture("project-indicator.json")
        self.assertIn(fixture["verificationStatus"], (
            "AUTO_EXTRACTED", "PARTIALLY_VERIFIED", "VERIFIED",
            "NEEDS_REVIEW",
        ))
        self.assertIn(fixture["completenessStatus"], (
            "COMPLETE", "PARTIAL", "UNKNOWN",
        ))
        if fixture["completenessStatus"] == "UNKNOWN":
            self.assertIsNone(fixture["evidenceId"])
        else:
            self.assertIsNotNone(fixture["evidenceId"])

    def test_fixture_preserves_unit_target_structure(self):
        """Acceptance: unit and target fields are present without inventing free text."""
        fixture = self.load_fixture("project-indicator.json")
        self.assertIsNotNone(fixture.get("indicatorUnit"))
        self.assertIn(fixture.get("targetDirection"), (
            "INCREASE", "DECREASE", "REACH", "MAINTAIN", None
        ))
        self.assertIn(fixture.get("targetPeriodType"), (
            "PER_PROJECT", "PER_YEAR", "PER_MONTH", "ONCE", None
        ))


if __name__ == "__main__":
    unittest.main()
