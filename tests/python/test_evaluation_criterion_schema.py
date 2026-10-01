import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class EvaluationCriterionSchemaTest(unittest.TestCase):
    """Dedicated contract tests for the EvaluationCriterion canonical schema.

    These tests verify that official evaluation/scoring criteria are modelled
    as a standalone entity separate from eligibility, with provenance, ordering,
    and verification metadata — never converted into custom "chances".
    """

    def setUp(self):
        self.schema_dir = ROOT / "schemas" / "v1"
        self.fixture_dir = ROOT / "tests" / "fixtures" / "canonical"

    def load_schema(self, name):
        return json.loads(
            (self.schema_dir / name).read_text(encoding="utf-8")
        )

    def load_fixture(self, name):
        return json.loads(
            (self.fixture_dir / name).read_text(encoding="utf-8")
        )

    def test_schema_exists_and_is_closed_versioned(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        self.assertEqual(schema["title"], "EvaluationCriterion")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["schemaVersion"]["const"], "1.0.0"
        )
        self.assertIn("schemaVersion", schema["required"])

    def test_required_fields_cover_official_fact_and_provenance(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        required = set(schema["required"])
        # Core identity and versioning always required.
        for field in (
            "schemaVersion", "id", "grantCallVersionId", "title",
            "sortOrder", "verificationStatus",
        ):
            self.assertIn(field, required, field)

    def test_criterion_type_is_official_enum(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        types = set(schema["properties"]["criterionType"]["enum"])
        self.assertEqual(
            types,
            {
                "EXCELLENCE", "IMPACT", "QUALITY", "FEASIBILITY",
                "BUDGET", "TEAM", "IMPLEMENTATION", "SUSTAINABILITY",
                "COMPLIANCE", "OTHER",
            },
        )

    def test_completeness_status_enum(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        statuses = set(
            schema["properties"]["completenessStatus"]["enum"]
        )
        self.assertEqual(statuses, {"COMPLETE", "PARTIAL", "UNKNOWN"})

    def test_verification_status_enum(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        statuses = set(
            schema["properties"]["verificationStatus"]["enum"]
        )
        self.assertEqual(
            statuses,
            {
                "AUTO_EXTRACTED", "PARTIALLY_VERIFIED",
                "VERIFIED", "NEEDS_REVIEW",
            },
        )

    def test_necessity_preserves_conditional_semantics(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        self.assertEqual(
            set(schema["properties"]["necessity"]["enum"]),
            {"REQUIRED", "CONDITIONAL", "RECOMMENDED"},
        )
        self.assertIn("conditionGroupId", schema["properties"])

    def test_no_chance_or_probability_fields(self):
        """Acceptance: explicit criteria must NOT become custom chances."""
        schema = self.load_schema("evaluation-criterion.schema.json")
        forbidden = {
            "probability", "chance", "likelihood", "score",
            "matchScore", "successRate", "confidenceScore",
        }
        self.assertFalse(
            forbidden & set(schema["properties"].keys()),
            f"schema must not contain chance/probability fields: "
            f"{forbidden & set(schema['properties'].keys())}",
        )

    def test_points_weight_threshold_are_nullable(self):
        """Acceptance: points/weight/threshold only present when explicit."""
        schema = self.load_schema("evaluation-criterion.schema.json")
        for field in ("pointsMax", "weight", "threshold"):
            prop = schema["properties"][field]
            self.assertIn("null", json.dumps(prop), field)
            minimum = prop.get("minimum")
            self.assertEqual(minimum, 0, field)

    def test_evidence_id_links_provenance(self):
        schema = self.load_schema("evaluation-criterion.schema.json")
        evidence = schema["properties"]["evidenceId"]
        self.assertIn("null", json.dumps(evidence))
        self.assertEqual(evidence.get("minLength"), 1)

    def test_fixture_matches_contract(self):
        fixture = self.load_fixture("evaluation-criterion.json")
        self.assertEqual(fixture["schemaVersion"], "1.0.0")

    def test_fixture_has_evidence_or_unknown(self):
        """Acceptance: every critical claim has evidence/UNKNOWN."""
        fixture = self.load_fixture("evaluation-criterion.json")
        self.assertIn(fixture["verificationStatus"], (
            "AUTO_EXTRACTED", "PARTIALLY_VERIFIED", "VERIFIED",
            "NEEDS_REVIEW",
        ))
        self.assertIn(fixture["completenessStatus"], (
            "COMPLETE", "PARTIAL", "UNKNOWN",
        ))
        # If completeness is UNKNOWN, evidence may be absent; otherwise evidence
        # should be present (or UNKNOWN itself).
        if fixture["completenessStatus"] == "UNKNOWN":
            self.assertIsNone(fixture["evidenceId"])
        else:
            self.assertIsNotNone(fixture["evidenceId"])


if __name__ == "__main__":
    unittest.main()
