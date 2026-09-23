import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseGateContractTest(unittest.TestCase):
    def test_beta_gate_preserves_human_usability_requirements(self):
        payload = json.loads(
            (ROOT / "release" / "beta-gate.json").read_text(encoding="utf-8")
        )
        manual = set(payload["manual"])
        for required in {
            "usability_obec",
            "usability_spolek",
            "usability_obcan",
            "usability_firma",
            "usability_skola",
            "critical_misunderstandings_resolved",
        }:
            self.assertIn(required, manual)

    def test_beta_gate_requires_accessibility_and_finance_evidence(self):
        payload = json.loads(
            (ROOT / "release" / "beta-gate.json").read_text(encoding="utf-8")
        )
        self.assertIn("accessibility_automation_green", payload["automated"])
        self.assertIn("finance_tests_green", payload["automated"])
        self.assertIn("screen_reader_walkthrough", payload["manual"])


if __name__ == "__main__":
    unittest.main()
