"""Error-scenario test: verify the lint toolchain catches real errors.

This test creates a temporary Python file with a deliberately
introduced lint violation (unused import) and verifies that Ruff
detects it. Runs only when Ruff is available (CI installs it);
skips gracefully otherwise.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class LintErrorScenarioTest(unittest.TestCase):
    """Demonstrate that the linter catches a known error pattern."""

    ruff: str

    def setUp(self):
        self.ruff = shutil.which("ruff") or ""
        if not self.ruff:
            self.skipTest("ruff is not installed in this environment")

    def test_ruff_detects_unused_import(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", dir=str(ROOT), delete=False
        ) as f:
            f.write("import os\n")
            f.write("x = 1\n")
            tmp_path = Path(f.name)

        try:
            result = subprocess.run(
                [self.ruff, "check", str(tmp_path)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertNotEqual(result.returncode, 0, "Ruff must detect unused import")
        self.assertIn(
            "F401", result.stdout, "Ruff should report F401 for unused import"
        )

    def test_ruff_detected_error_is_evidence_not_guesswork(self):
        """Verify the detected error is a real code issue, not a false positive."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", dir=str(ROOT), delete=False
        ) as f:
            f.write("def foo():\n")
            f.write("    import sys\n")
            f.write("    return 42\n")
            tmp_path = Path(f.name)

        try:
            result = subprocess.run(
                [self.ruff, "check", str(tmp_path)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertEqual(
            result.returncode, 0, "sys in a function scope is not unused"
        )


if __name__ == "__main__":
    unittest.main()
