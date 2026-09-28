import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prerequisites.mjs"


class PrerequisitesTest(unittest.TestCase):
    """Tests for the local-development prerequisites check.

    See docs/LOCAL_DEVELOPMENT.md for the full guide.
    """

    def test_script_exists(self):
        self.assertTrue(
            SCRIPT.exists(),
            f"prerequisites script missing at {SCRIPT}",
        )

    def test_script_syntax_valid(self):
        result = subprocess.run(
            ["node", "--check", str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, f"syntax error: {result.stderr}")

    def test_script_passes_when_all_prerequisites_present(self):
        result = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            f"prerequisites check failed:\n{result.stdout}\n{result.stderr}",
        )
        # Output should mention each check.
        for keyword in ("Node.js", "npm", "Python 3"):
            self.assertIn(keyword, result.stdout)

    def test_error_scenario_missing_python3_fails_clearly(self):
        """Error scenario: when python3 is not on PATH the check must fail."""
        node_path = shutil.which("node")
        self.assertIsNotNone(node_path, "node must be available for this test")
        assert node_path is not None  # for type-checkers
        node_dir = str(Path(node_path).parent)

        python3_path = shutil.which("python3")
        if python3_path is None:
            self.skipTest("python3 not found — cannot test missing-python3 scenario")
        python3_dir = str(Path(python3_path).parent)

        # Locate ALL PATH entries that contain a python3 binary and remove them.
        python3_dirs = set()
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d and os.path.isfile(os.path.join(d, "python3")):
                python3_dirs.add(d)

        # If every PATH entry that contains python3 also contains node, we
        # cannot simulate a missing-python3 scenario — skip.
        if python3_dirs and node_dir in python3_dirs and len(python3_dirs) == 1:
            self.skipTest(
                "python3 and node share their only common PATH entry — "
                "cannot simulate missing python3"
            )

        # Build a PATH that contains node_dir but none of the python3 directories.
        path_dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
        path_dirs = [d for d in path_dirs if d not in python3_dirs]
        if node_dir not in path_dirs:
            path_dirs.insert(0, node_dir)
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join(path_dirs)

        result = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        self.assertNotEqual(
            result.returncode, 0,
            "script should fail when python3 is missing",
        )
        self.assertIn("Python 3", result.stdout)


if __name__ == "__main__":
    unittest.main()
