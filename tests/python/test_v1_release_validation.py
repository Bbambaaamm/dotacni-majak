import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_v1_release.py"
SPEC = importlib.util.spec_from_file_location("validate_v1_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def check(status="PASS"):
    return {"status": status, "evidence": "https://example.test/evidence"}


def valid_gate():
    return {
        "schemaVersion": "1.0",
        "release": {
            "version": "1.0.0",
            "sha": "a" * 40,
            "candidateBuiltAt": "2026-09-23T22:00:00Z",
        },
        "automated": {key: check() for key in MODULE.REQUIRED_AUTOMATED},
        "manual": {key: check() for key in MODULE.REQUIRED_MANUAL},
        "knownLimitations": [
            {
                "id": "LIMIT-1",
                "summary": "Known and documented source coverage boundary.",
                "publiclyDisclosed": True,
                "riskAccepted": True,
            }
        ],
        "decision": {
            "status": "GO",
            "reviewedAt": "2026-09-23",
            "reviewer": "release-review",
            "rationale": "All release gates have evidence.",
        },
    }


class V1ReleaseValidationTest(unittest.TestCase):
    def test_complete_evidence_passes_gate(self):
        self.assertEqual(MODULE.validate_document(valid_gate(), require_gate=True), [])

    def test_beta_usability_cannot_be_pending(self):
        payload = valid_gate()
        payload["manual"]["betaUsability"] = {"status": "PENDING", "evidence": ""}
        errors = MODULE.validate_document(payload, require_gate=True)
        self.assertTrue(any("manual.betaUsability" in error for error in errors))

    def test_unknown_check_name_is_rejected(self):
        payload = valid_gate()
        payload["automated"]["invented"] = check()
        errors = MODULE.validate_document(payload, require_gate=False)
        self.assertTrue(any("unknown checks" in error for error in errors))

    def test_unaccepted_limitation_blocks_release(self):
        payload = valid_gate()
        payload["knownLimitations"][0]["riskAccepted"] = False
        errors = MODULE.validate_document(payload, require_gate=True)
        self.assertTrue(any("risk accepted" in error for error in errors))

    def test_structure_mode_does_not_fake_release_go(self):
        payload = deepcopy(valid_gate())
        payload["decision"] = {
            "status": "PENDING",
            "reviewedAt": None,
            "reviewer": "",
            "rationale": "",
        }
        for group in ("automated", "manual"):
            for value in payload[group].values():
                value["status"] = "PENDING"
                value["evidence"] = ""
        self.assertEqual(MODULE.validate_document(payload, require_gate=False), [])
        self.assertNotEqual(MODULE.validate_document(payload, require_gate=True), [])


if __name__ == "__main__":
    unittest.main()
