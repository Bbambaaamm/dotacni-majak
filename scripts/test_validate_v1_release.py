"""
Test suite for the v1.0 Release Gate validator (scripts/validate_v1_release.py).

This suite verifies that the validator's fail-closed logic is correct:
- A fully-valid evidence document passes with --require-gate
- Any missing required check, invalid status, empty evidence, or wrong decision
  causes a validation error
- Structure mode (no --require-gate) is more permissive than gate mode

Run with:
    python3 -m pytest scripts/test_validate_v1_release.py
  or
    python3 -m unittest scripts.test_validate_v1_release
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Load the validator module from scripts/validate_v1_release.py (not a package)
_spec = importlib.util.spec_from_file_location(
    "validate_v1_release",
    ROOT / "scripts" / "validate_v1_release.py",
)
assert _spec is not None and _spec.loader is not None
_validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validator)

VALID_SHA = "0123456789abcdef0123456789abcdef01234567"


def _make_checks(status: str = "PASS", evidence: str = "https://example.test/evidence") -> dict[str, Any]:
    """Create automated + manual check dicts with all required checks present."""
    automated = {
        name: {"status": status, "evidence": evidence}
        for name in _validator.REQUIRED_AUTOMATED
    }
    manual = {
        name: {"status": status, "evidence": evidence}
        for name in _validator.REQUIRED_MANUAL
    }
    return {"automated": automated, "manual": manual}


def _make_valid_payload(**overrides: Any) -> dict[str, Any]:
    """Build a fully-valid evidence document (passes gate mode)."""
    checks = _make_checks()
    payload: dict[str, Any] = {
        "schemaVersion": "1.0",
        "release": {
            "version": "1.0.0",
            "sha": VALID_SHA,
            "candidateBuiltAt": "2026-09-23T22:00:00Z",
        },
        "automated": checks["automated"],
        "manual": checks["manual"],
        "knownLimitations": [],
        "decision": {
            "status": "GO",
            "reviewedAt": "2026-09-23T22:00:00Z",
            "reviewer": "Release Coordinator",
            "rationale": "All gates passed.",
        },
    }
    payload.update(overrides)
    return payload


class TestValidDocument(unittest.TestCase):
    """A well-formed evidence document must pass both structure and gate modes."""

    def test_valid_document_passes_structure_mode(self) -> None:
        payload = _make_valid_payload()
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertEqual(errors, [], f"Expected no errors, got: {errors}")

    def test_valid_document_passes_gate_mode(self) -> None:
        payload = _make_valid_payload()
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertEqual(errors, [], f"Expected no errors in gate mode, got: {errors}")


class TestMissingChecks(unittest.TestCase):
    """Missing required checks must always be flagged."""

    def test_missing_automated_check_fails(self) -> None:
        checks = _make_checks()
        # Remove one required automated check
        first_auto = sorted(_validator.REQUIRED_AUTOMATED)[0]
        del checks["automated"][first_auto]
        payload = _make_valid_payload(automated=checks["automated"])
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("automated" in e or first_auto in e for e in errors),
            f"Expected missing-check error for {first_auto}, got: {errors}",
        )

    def test_missing_manual_check_fails(self) -> None:
        checks = _make_checks()
        first_manual = sorted(_validator.REQUIRED_MANUAL)[0]
        del checks["manual"][first_manual]
        payload = _make_valid_payload(manual=checks["manual"])
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any(first_manual in e for e in errors),
            f"Expected missing-check error for {first_manual}, got: {errors}",
        )

    def test_extra_unknown_check_fails(self) -> None:
        payload = _make_valid_payload()
        payload["automated"]["unknown_check"] = {"status": "PASS", "evidence": "x"}
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("unknown_check" in e for e in errors),
            f"Expected unknown-check error, got: {errors}",
        )


class TestCheckStatusAndEvidence(unittest.TestCase):
    """Gate mode requires every check to be PASS or ACCEPTED_LIMITATION with evidence."""

    def test_pending_status_fails_gate(self) -> None:
        checks = _make_checks()
        first_auto = sorted(_validator.REQUIRED_AUTOMATED)[0]
        checks["automated"][first_auto] = {"status": "PENDING", "evidence": "https://example.test"}
        payload = _make_valid_payload(automated=checks["automated"])
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any(first_auto in e for e in errors),
            f"Expected status error for {first_auto}, got: {errors}",
        )

    def test_empty_evidence_fails_gate(self) -> None:
        checks = _make_checks()
        first_manual = sorted(_validator.REQUIRED_MANUAL)[0]
        checks["manual"][first_manual] = {"status": "PASS", "evidence": ""}
        payload = _make_valid_payload(manual=checks["manual"])
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any(f"manual.{first_manual}" in e for e in errors),
            f"Expected evidence error for {first_manual}, got: {errors}",
        )

    def test_pending_status_passes_structure_mode(self) -> None:
        """Without --require-gate, PENDING is allowed (structure-only check)."""
        payload = _make_valid_payload()
        # All checks are PASS — but let's make one PENDING
        payload["automated"]["ci"] = {"status": "PENDING", "evidence": ""}
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertEqual(errors, [], f"Expected structure mode to allow PENDING, got: {errors}")

    def test_accepted_limitation_passes_gate(self) -> None:
        """ACCEPTED_LIMITATION status with proper limitation is acceptable."""
        checks = _make_checks()
        first_auto = sorted(_validator.REQUIRED_AUTOMATED)[0]
        checks["automated"][first_auto] = {
            "status": "ACCEPTED_LIMITATION",
            "evidence": "https://example.test/limitation",
        }
        # Add a matching accepted limitation
        payload = _make_valid_payload(automated=checks["automated"])
        payload["knownLimitations"] = [
            {
                "id": "limit-auto-" + first_auto,
                "summary": "Known limitation for testing",
                "publiclyDisclosed": True,
                "riskAccepted": True,
            }
        ]
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertEqual(errors, [], f"Expected ACCEPTED_LIMITATION to pass, got: {errors}")


class TestDecisionBlock(unittest.TestCase):
    """Gate mode requires an explicit GO decision with reviewer + rationale."""

    def test_no_go_decision_fails_gate(self) -> None:
        payload = _make_valid_payload()
        payload["decision"]["status"] = "NO_GO"
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("decision.status" in e for e in errors),
            f"Expected decision error, got: {errors}",
        )

    def test_pending_decision_fails_gate(self) -> None:
        payload = _make_valid_payload()
        payload["decision"]["status"] = "PENDING"
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("decision.status" in e for e in errors),
            f"Expected decision error, got: {errors}",
        )

    def test_missing_reviewed_at_fails_gate(self) -> None:
        payload = _make_valid_payload()
        payload["decision"]["reviewedAt"] = None
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("reviewedAt" in e for e in errors),
            f"Expected reviewedAt error, got: {errors}",
        )

    def test_missing_reviewer_fails_gate(self) -> None:
        payload = _make_valid_payload()
        payload["decision"]["reviewer"] = ""
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("reviewer" in e for e in errors),
            f"Expected reviewer error, got: {errors}",
        )

    def test_missing_rationale_fails_gate(self) -> None:
        payload = _make_valid_payload()
        payload["decision"]["rationale"] = ""
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("rationale" in e for e in errors),
            f"Expected rationale error, got: {errors}",
        )


class TestKnownLimitations(unittest.TestCase):
    """Known limitations must be disclosed and risk-accepted in gate mode."""

    def test_undisclosed_limitation_fails_gate(self) -> None:
        payload = _make_valid_payload()
        payload["knownLimitations"] = [
            {
                "id": "LIMIT-TEST",
                "summary": "Test limitation",
                "publiclyDisclosed": False,
                "riskAccepted": False,
            }
        ]
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(
            any("publicly disclosed" in e.lower() or "risk" in e.lower() for e in errors),
            f"Expected limitation disclosure error, got: {errors}",
        )

    def test_no_limitations_passes_gate(self) -> None:
        """No known limitations is the ideal state — passes cleanly."""
        payload = _make_valid_payload(knownLimitations=[])
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertEqual(errors, [], f"Expected no errors with empty limitations, got: {errors}")

    def test_duplicate_limitation_id_fails(self) -> None:
        payload = _make_valid_payload()
        payload["knownLimitations"] = [
            {"id": "DUP", "summary": "A", "publiclyDisclosed": True, "riskAccepted": True},
            {"id": "DUP", "summary": "B", "publiclyDisclosed": True, "riskAccepted": True},
        ]
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("duplicate" in e.lower() for e in errors),
            f"Expected duplicate-id error, got: {errors}",
        )

    def test_missing_limitation_summary_fails(self) -> None:
        payload = _make_valid_payload()
        payload["knownLimitations"] = [
            {"id": "LIMIT-TEST", "summary": "", "publiclyDisclosed": True, "riskAccepted": True}
        ]
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("summary" in e for e in errors),
            f"Expected summary error, got: {errors}",
        )


class TestReleaseMetadata(unittest.TestCase):
    """Release metadata must be well-formed."""

    def test_invalid_sha_fails(self) -> None:
        payload = _make_valid_payload()
        payload["release"]["sha"] = "not-a-sha"
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("sha" in e.lower() for e in errors),
            f"Expected SHA format error, got: {errors}",
        )

    def test_short_sha_fails(self) -> None:
        payload = _make_valid_payload()
        payload["release"]["sha"] = "abc123"
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("sha" in e.lower() for e in errors),
            f"Expected SHA format error, got: {errors}",
        )

    def test_missing_version_fails(self) -> None:
        payload = _make_valid_payload()
        payload["release"]["version"] = ""
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("version" in e.lower() for e in errors),
            f"Expected version error, got: {errors}",
        )

    def test_wrong_schema_version_fails(self) -> None:
        payload = _make_valid_payload()
        payload["schemaVersion"] = "0.9"
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("schema" in e.lower() for e in errors),
            f"Expected schema version error, got: {errors}",
        )


class TestFailClosedOnAmbiguity(unittest.TestCase):
    """The validator must fail-closed on malformed or ambiguous input."""

    def test_null_env_fails_closed(self) -> None:
        errors = _validator.validate_document(None, require_gate=True)  # type: ignore[arg-type]
        self.assertTrue(len(errors) > 0, "Expected errors for null payload")

    def test_non_object_automated_fails(self) -> None:
        payload = _make_valid_payload()
        payload["automated"] = "all-pass"
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("automated must be an object" in e for e in errors),
            f"Expected type error, got: {errors}",
        )

    def test_non_object_manual_fails(self) -> None:
        payload = _make_valid_payload()
        payload["manual"] = 42
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("manual must be an object" in e for e in errors),
            f"Expected type error, got: {errors}",
        )

    def test_non_dict_check_fails(self) -> None:
        payload = _make_valid_payload()
        first_auto = sorted(_validator.REQUIRED_AUTOMATED)[0]
        payload["automated"][first_auto] = "PASS"
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any(f"automated.{first_auto}" in e for e in errors),
            f"Expected type error for check object, got: {errors}",
        )

    def test_invalid_check_status_fails(self) -> None:
        payload = _make_valid_payload()
        first_manual = sorted(_validator.REQUIRED_MANUAL)[0]
        payload["manual"][first_manual] = {"status": "MAYBE", "evidence": "x"}
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any(f"manual.{first_manual}" in e for e in errors),
            f"Expected invalid-status error, got: {errors}",
        )

    def test_null_known_limitations_fails(self) -> None:
        payload = _make_valid_payload()
        payload["knownLimitations"] = None  # type: ignore[assignment]
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("knownLimitations must be a list" in e for e in errors),
            f"Expected type error, got: {errors}",
        )

    def test_null_decision_fails(self) -> None:
        payload = _make_valid_payload()
        payload["decision"] = None
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertTrue(
            any("decision must be an object" in e for e in errors),
            f"Expected type error, got: {errors}",
        )


class TestExampleFile(unittest.TestCase):
    """The example evidence file must pass structure validation."""

    def test_example_passes_structure_mode(self) -> None:
        example = ROOT / "release" / "v1-evidence.example.json"
        payload = _validator.load(example)
        errors = _validator.validate_document(payload, require_gate=False)
        self.assertEqual(errors, [], f"Example file should pass structure validation, got: {errors}")

    def test_example_fails_gate_mode(self) -> None:
        """The example file has PENDING statuses — must fail in gate mode."""
        example = ROOT / "release" / "v1-evidence.example.json"
        payload = _validator.load(example)
        errors = _validator.validate_document(payload, require_gate=True)
        self.assertTrue(len(errors) > 0, "Example file should fail in gate mode (all PENDING)")


if __name__ == "__main__":
    unittest.main()
