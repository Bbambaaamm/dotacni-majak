"""Validate that the lint/format toolchain config files exist and are well-formed.

These tests verify the process is reproducible (config as code) and
documented — a subset of issue #504 acceptance criteria.
"""

import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class LintConfigFilesTest(unittest.TestCase):
    """Every config file must exist and be parseable."""

    def test_ruff_toml_is_valid_and_configured(self):
        path = ROOT / "ruff.toml"
        self.assertTrue(path.exists(), "ruff.toml is missing")
        with open(path, "rb") as f:
            data = tomllib.load(f)
        self.assertIn("lint", data, "ruff.toml must define [lint]")
        self.assertIn("select", data["lint"], "ruff.toml [lint] must have 'select'")
        self.assertIn("format", data, "ruff.toml must define [format]")

    def test_eslint_config_is_present(self):
        path = ROOT / "eslint.config.js"
        self.assertTrue(path.exists(), "eslint.config.js is missing")
        content = path.read_text(encoding="utf-8")
        self.assertIn("eslint", content.lower())
        self.assertIn("typescript", content.lower())

    def test_prettierrc_is_valid_json(self):
        path = ROOT / ".prettierrc"
        self.assertTrue(path.exists(), ".prettierrc is missing")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertIn("semi", data)
        self.assertIn("singleQuote", data)

    def test_precommit_config_is_valid_yaml(self):
        path = ROOT / ".pre-commit-config.yaml"
        self.assertTrue(path.exists(), ".pre-commit-config.yaml is missing")
        content = path.read_text(encoding="utf-8")
        self.assertIn("repos:", content)
        self.assertIn("ruff", content)

    def test_package_json_has_lint_and_format_scripts(self):
        path = ROOT / "package.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        for key in ("lint", "lint:fix", "format", "format:check", "lint:py",
                     "format:py", "format:py:check", "lint:all"):
            self.assertIn(key, scripts, f"package.json scripts missing '{key}'")

    def test_linting_documentation_exists(self):
        path = ROOT / "docs" / "LINTING.md"
        self.assertTrue(path.exists(), "docs/LINTING.md is missing")
        content = path.read_text(encoding="utf-8")
        self.assertIn("ruff", content.lower())
        self.assertIn("eslint", content.lower())
        self.assertIn("prettier", content.lower())


if __name__ == "__main__":
    unittest.main()
