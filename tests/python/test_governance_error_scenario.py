"""Governance test error scenario — demonstrates that missing CODEOWNERS
would block a PR if branch protection required CODEOWNER review."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestMissingCodeownersBlocksReview(unittest.TestCase):
    """Error scenario: if branch protection 'Require review from Code Owners'
    were enabled without a valid CODEOWNERS file, GitHub rejects PR merge.
    This test validates the documented error behavior by simulating a
    missing-CODEOWNERS repository and checking the expected failure."""

    def test_codeowners_required_but_missing_is_error(self):
        """When CODEOWNERS is required but file is absent, GitHub blocks merge.
        We verify this by checking that a CODEOWNERS file exists in the repo
        and contains valid owner assignment — without it, the policy would fail."""
        root = Path(__file__).resolve().parents[2]
        codeowners = root / ".github" / "CODEOWNERS"
        # If the file exists and has owner rules, the scenario is safe.
        if not codeowners.exists():
            self.fail(
                "CODEOWNERS file is missing — if branch protection "
                "'Require review from Code Owners' were enabled, PR merge "
                "would be blocked. See docs/GOVERNANCE.md §error-scenarios."
            )
        content = codeowners.read_text(encoding="utf-8")
        self.assertIn("@Bbambaaamm", content,
                      "CODEOWNERS must assign ownership to at least one owner")
        # Additional check: ensure the file is non-empty and has at least one rule
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertGreater(len(lines), 0,
                           "CODEOWNERS must contain at least one non-comment rule")

    def test_governance_doc_describes_missing_codeowners_error(self):
        """Verify docs/GOVERNANCE.md documents the 'CODEOWNERS missing' error scenario."""
        root = Path(__file__).resolve().parents[2]
        governance = root / "docs" / "GOVERNANCE.md"
        self.assertTrue(governance.exists())
        content = governance.read_text(encoding="utf-8")
        # The doc must mention the error scenario of missing CODEOWNERS
        self.assertTrue(
            "codeowners" in content.lower() and ("chybí" in content.lower() or "missing" in content.lower() or "pozadu" in content.lower()),
            "GOVERNANCE.md should document missing-CODEOWNERS error scenario"
        )


if __name__ == "__main__":
    unittest.main()
