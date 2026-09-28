"""
Tests for governance prerequisites:
- .github/CODEOWNERS existence and structure
- docs/GOVERNANCE.md existence and structure
- CI foundation checks availability (runs-on, steps existence in ci.yml)
- Error scenario: missing CODEOWNERS when branch protection would require it
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path


class TestGovernancePrerequisites(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def _repo_path(self, *parts):
        return self.ROOT / *parts

    def test_codeowners_file_exists(self):
        codeowners = self._repo_path(".github", "CODEOWNERS")
        self.assertTrue(codeowners.exists(), "CODEOWNERS file missing")

    def test_codeowners_has_owner_rule(self):
        codeowners = self._repo_path(".github", "CODEOWNERS")
        content = codeowners.read_text(encoding="utf-8")
        self.assertIn("@Bbambaaamm", content, "CODEOWNERS must assign ownership to repo owner")

    def test_codeowners_covers_critical_paths(self):
        codeowners = self._repo_path(".github", "CODEOWNERS")
        content = codeowners.read_text(encoding="utf-8")
        required_paths = ["schemas/", "migrations/", ".github/", "apps/", "connectors/", "packages/", "pipelines/", "scripts/", "docs/"]
        for path in required_paths:
            self.assertIn(path, content, f"CODEOWNERS missing coverage for critical path: {path}")

    def test_governance_doc_exists(self):
        governance = self._repo_path("docs", "GOVERNANCE.md")
        self.assertTrue(governance.exists(), "GOVERNANCE.md documentation missing")

    def test_governance_doc_describes_branch_protection(self):
        governance = self._repo_path("docs", "GOVERNANCE.md")
        content = governance.read_text(encoding="utf-8")
        self.assertIn("branch protection", content.lower(), "GOVERNANCE.md must describe branch protection policy")
        self.assertIn("required status checks", content.lower(), "GOVERNANCE.md must describe required checks")

    def test_governance_doc_describes_codeowners(self):
        governance = self._repo_path("docs", "GOVERNANCE.md")
        content = governance.read_text(encoding="utf-8")
        self.assertIn("CODEOWNERS", content, "GOVERNANCE.md must describe CODEOWNERS system")

    def test_governance_doc_describes_merge_politics(self):
        governance = self._repo_path("docs", "GOVERNANCE.md")
        content = governance.read_text(encoding="utf-8")
        self.assertIn("squash", content.lower(), "GOVERNANCE.md must document squash merge policy")

    def test_governance_doc_has_error_scenarios(self):
        governance = self._repo_path("docs", "GOVERNANCE.md")
        content = governance.read_text(encoding="utf-8")
        self.assertIn("error scenario", content.lower(), "GOVERNANCE.md must document error scenarios")
        self.assertIn("ci neprošel", content.lower(), "GOVERNANCE.md must describe CI failure scenario")

    def test_governance_doc_has_audit_evidence_section(self):
        governance = self._repo_path("docs", "GOVERNANCE.md")
        content = governance.read_text(encoding="utf-8")
        self.assertIn("audit", content.lower(), "GOVERNANCE.md must describe audit evidence availability")

    def test_ci_foundation_job_exists(self):
        ci_path = self._repo_path(".github", "workflows", "ci.yml")
        self.assertTrue(ci_path.exists(), "ci.yml missing — CI foundation prerequisite not satisfied")
        import yaml
        with ci_path.open(encoding="utf-8") as f:
            ci = yaml.safe_load(f)
        jobs = ci.get("jobs", {})
        self.assertIn("foundation", jobs, "ci.yml must have 'foundation' job for required checks policy")

    def test_ci_foundation_has_typecheck_steps(self):
        ci_path = self._repo_path(".github", "workflows", "ci.yml")
        import yaml
        with ci_path.open(encoding="utf-8") as f:
            ci = yaml.safe_load(f)
        steps = ci["jobs"]["foundation"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        self.assertTrue(any("typecheck" in n.lower() for n in step_names),
                        "CI foundation must include typecheck steps")

    def test_ci_foundation_has_test_steps(self):
        ci_path = self._repo_path(".github", "workflows", "ci.yml")
        import yaml
        with ci_path.open(encoding="utf-8") as f:
            ci = yaml.safe_load(f)
        steps = ci["jobs"]["foundation"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        self.assertTrue(any("test" in n.lower() for n in step_names),
                        "CI foundation must include test steps")


if __name__ == "__main__":
    unittest.main()
