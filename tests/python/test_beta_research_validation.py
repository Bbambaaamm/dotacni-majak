import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_beta_research.py"
SPEC = importlib.util.spec_from_file_location("validate_beta_research", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def session(identifier: str, segment: str, tasks=("A", "B", "C", "D", "E", "F")):
    return {
        "id": identifier,
        "segment": segment,
        "conductedAt": "2026-09-23",
        "tasks": [
            {
                "id": task,
                "completedWithoutHelp": True,
                "criticalMisunderstanding": False,
                "sourceFound": True,
                "correctNextAction": True,
                "notes": "",
            }
            for task in tasks
        ],
    }


def valid_gate():
    return {
        "schemaVersion": "1.0",
        "studyId": "beta-test",
        "decision": {
            "status": "GO",
            "reviewedAt": "2026-09-23",
            "rationale": "All representative segments completed critical flows.",
        },
        "sessions": [
            session("s1", "OBEC"),
            session("s2", "SPOLEK"),
            session("s3", "OBCAN"),
            session("s4", "FIRMA"),
            session("s5", "SKOLA"),
        ],
        "findings": [],
    }


class BetaResearchValidationTest(unittest.TestCase):
    def test_complete_human_evidence_passes_gate(self):
        self.assertEqual(MODULE.validate_document(valid_gate(), require_gate=True), [])

    def test_missing_segment_blocks_gate(self):
        payload = valid_gate()
        payload["sessions"] = payload["sessions"][:-1]
        errors = MODULE.validate_document(payload, require_gate=True)
        self.assertTrue(any("SKOLA" in error for error in errors))

    def test_open_p1_blocks_gate(self):
        payload = valid_gate()
        payload["findings"] = [
            {"id": "F-1", "severity": "P1", "status": "OPEN"}
        ]
        errors = MODULE.validate_document(payload, require_gate=True)
        self.assertTrue(any("F-1" in error for error in errors))

    def test_automated_structure_mode_does_not_fake_human_gate(self):
        payload = {
            "schemaVersion": "1.0",
            "studyId": "draft",
            "decision": {"status": "PENDING", "reviewedAt": None, "rationale": ""},
            "sessions": [],
            "findings": [],
        }
        self.assertEqual(
            MODULE.validate_document(payload, require_gate=False),
            [],
        )
        self.assertNotEqual(
            MODULE.validate_document(payload, require_gate=True),
            [],
        )


if __name__ == "__main__":
    unittest.main()
