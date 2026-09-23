import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class V1ReleaseGateContractTest(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(
            (ROOT / "release" / "v1-gate.json").read_text(encoding="utf-8")
        )

    def test_v1_depends_on_public_beta(self):
        self.assertIn("public-beta", self.payload["dependsOn"])

    def test_manual_security_accessibility_and_recovery_reviews_are_required(self):
        manual = set(self.payload["manual"])
        for required in {
            "screen_reader_audit",
            "privacy_review",
            "security_threat_review",
            "source_coverage_audit",
            "recovery_runbook_tabletop",
            "backup_export_restore_verified",
        }:
            self.assertIn(required, manual)

    def test_release_evidence_is_bound_to_exact_candidate(self):
        evidence = set(self.payload["releaseEvidence"])
        self.assertIn("release_sha", evidence)
        self.assertIn("review_date", evidence)
        self.assertIn("evidence_links", evidence)


if __name__ == "__main__":
    unittest.main()
