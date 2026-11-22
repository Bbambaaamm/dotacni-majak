import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GrantSubmissionSchemaTest(unittest.TestCase):
    """Contract tests for the GrantSubmission canonical schema.

    GrantSubmission captures the practical information a candidate needs to
    submit an application for a given GrantCallVersion: submission portal URL,
    application method, account/signature requirements, and the provider's
    public contact details. Each claim carries provenance (evidenceId) plus
    completeness and verification status, so the UI never presents a
    user-supplied guess as an official fact.

    Modeled as the M1 model-first counterpart to the GrantEvaluationCriterion
    entity: schema + migration + fixture + tests only — no ingestion wiring.
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
        schema = self.load_schema("grant-submission.schema.json")
        self.assertEqual(schema["title"], "GrantSubmission")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["schemaVersion"]["const"], "1.0.0"
        )
        self.assertIn("schemaVersion", schema["required"])

    def test_required_fields_cover_identity_and_provenance(self):
        schema = self.load_schema("grant-submission.schema.json")
        required = set(schema["required"])
        # Identity + provenance metadata always required.
        for field in (
            "schemaVersion", "id", "grantCallVersionId",
            "completenessStatus", "verificationStatus",
        ):
            self.assertIn(field, required, field)
        # Submission-specific fields are conditional: nullable, so that
        # absence/unknown is representable rather than fabricating data.
        for field in (
            "portalUrl", "applicationMethod", "accountRequirement",
            "signatureRequirement", "contactName", "contactRole",
            "contactEmail", "contactPhone", "evidenceId",
        ):
            self.assertNotIn(field, required, field)

    def test_application_method_is_official_enum(self):
        schema = self.load_schema("grant-submission.schema.json")
        methods = set(schema["properties"]["applicationMethod"]["enum"])
        self.assertEqual(
            methods,
            {"ELECTRONIC", "PAPER", "HYBRID", "EMAIL", "POSTAL", "OTHER"},
        )

    def test_completeness_status_enum(self):
        schema = self.load_schema("grant-submission.schema.json")
        statuses = set(schema["properties"]["completenessStatus"]["enum"])
        self.assertEqual(statuses, {"COMPLETE", "PARTIAL", "UNKNOWN"})

    def test_verification_status_enum(self):
        schema = self.load_schema("grant-submission.schema.json")
        statuses = set(schema["properties"]["verificationStatus"]["enum"])
        self.assertEqual(
            statuses,
            {"AUTO_EXTRACTED", "PARTIALLY_VERIFIED",
             "VERIFIED", "NEEDS_REVIEW"},
        )

    def test_no_chance_or_probability_fields(self):
        """Acceptace: explicitní údaje se nepřevádějí na „šanci“."""
        schema = self.load_schema("grant-submission.schema.json")
        forbidden = {
            "probability", "chance", "likelihood", "score",
            "matchScore", "successRate", "confidenceScore",
            "eligible", "successChance",
        }
        self.assertFalse(
            forbidden & set(schema["properties"].keys()),
            f"schema must not contain chance/eligibility fields: "
            f"{forbidden & set(schema['properties'].keys())}",
        )

    def test_submission_fields_are_nullable(self):
        """Acceptace: explicitní kritéria jsou null, když neuvedena."""
        schema = self.load_schema("grant-submission.schema.json")
        for field in (
            "portalUrl", "applicationMethod", "accountRequirement",
            "signatureRequirement", "contactName", "contactRole",
            "contactEmail", "contactPhone", "evidenceId",
        ):
            prop = schema["properties"][field]
            self.assertIn(
                "null", json.dumps(prop),
                f"{field} must be nullable so UNKNOWN is representable",
            )

    def test_portal_url_is_nullable_uri(self):
        schema = self.load_schema("grant-submission.schema.json")
        prop = schema["properties"]["portalUrl"]
        self.assertIn("null", json.dumps(prop))
        self.assertEqual(prop.get("format"), "uri")

    def test_contact_email_is_nullable_email(self):
        schema = self.load_schema("grant-submission.schema.json")
        prop = schema["properties"]["contactEmail"]
        self.assertIn("null", json.dumps(prop))
        self.assertEqual(prop.get("format"), "email")

    def test_evidence_id_links_provenance(self):
        schema = self.load_schema("grant-submission.schema.json")
        evidence = schema["properties"]["evidenceId"]
        self.assertIn("null", json.dumps(evidence))
        self.assertEqual(evidence.get("minLength"), 1)

    def test_fixture_matches_contract(self):
        fixture = self.load_fixture("grant-submission.json")
        self.assertEqual(fixture["schemaVersion"], "1.0.0")
        self.assertEqual(fixture["id"], "submission:test-call-v1")

    def test_fixture_has_evidence_or_unknown(self):
        """Acceptace: každé kritické tvrzení má evidence/UNKNOWN."""
        fixture = self.load_fixture("grant-submission.json")
        self.assertIn(fixture["verificationStatus"], (
            "AUTO_EXTRACTED", "PARTIALLY_VERIFIED", "VERIFIED",
            "NEEDS_REVIEW",
        ))
        self.assertIn(fixture["completenessStatus"], (
            "COMPLETE", "PARTIAL", "UNKNOWN",
        ))
        # If completeness is UNKNOWN, evidence may be absent; otherwise an
        # evidence anchor must be present so the claim is accountable.
        if fixture["completenessStatus"] == "UNKNOWN":
            self.assertIsNone(fixture["evidenceId"])
        else:
            self.assertIsNotNone(fixture["evidenceId"])


if __name__ == "__main__":
    unittest.main()
