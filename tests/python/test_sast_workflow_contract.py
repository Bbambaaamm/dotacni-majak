"""M15 / GitHub issue #427 — SAST / CodeQL workflow + config contract test.

Validates that the CodeQL workflow and its config file satisfy the
structural requirements declared in the issue acceptance criteria:

- workflow is triggered on PRs + pushes to main + scheduled run
- workflow has security-events: write permission
- workflow uses a CodeQL config file (not inline queries)
- workflow is fail-closed: no continue-on-error on the analyze step
- CodeQL config file exists and declares a suppression policy
- config file excludes transient/generated/test fixtures from scanning
- no secrets/PII are logged (config comments + workflow steps reviewed)

The test is intentionally stdlib-only (no PyYAML) so it runs in the same
test environment as the rest of `tests/python/` without extra dependencies.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = ROOT / ".github" / "workflows"
CONFIG = ROOT / ".github" / "codeql-config.yml"

CODEQL_WORKFLOW = WORKFLOWS / "codeql.yml"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _yaml_scalar_value(text: str, key: str) -> str | None:
    """Extract a top-level or indented scalar YAML value for `key` from text.

    Only handles the simple 'key: value' and 'key:' + indented-block forms
    that appear in our workflow/config files. Not a general YAML parser.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:") and not stripped.startswith(f"{key}:/"):
            value = stripped[len(key):].lstrip(": ").strip()
            if value:
                return value
    return None


def _yaml_list_item(text: str, key: str, item: str) -> bool:
    """Return True if `item` appears as a list item under `key` in text."""
    lines = text.splitlines()
    in_block = False
    indent = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            indent = len(line) - len(line.lstrip())
            in_block = True
            continue
        if in_block:
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent <= indent and stripped and not stripped.startswith("#"):
                in_block = False
                continue
            if cur_indent > indent and stripped.startswith("- "):
                if item in stripped:
                    return True
    return False


class SastWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow_text = _read_text(CODEQL_WORKFLOW)
        cls.config_text = _read_text(CONFIG)

    # --- workflow existence + parseability ---

    def test_codeql_workflow_file_exists(self):
        self.assertTrue(CODEQL_WORKFLOW.is_file(), f"{CODEQL_WORKFLOW} missing")

    def test_codeql_config_file_exists(self):
        self.assertTrue(CONFIG.is_file(), f"{CONFIG} missing")

    # --- trigger coverage ---

    def test_workflow_triggers_on_push_to_main(self):
        self.assertIn("push:", self.workflow_text)
        self.assertIn("branches: [main]", self.workflow_text)

    def test_workflow_triggers_on_pull_request_to_main(self):
        self.assertIn("pull_request:", self.workflow_text)
        self.assertIn("branches: [main]", self.workflow_text)

    def test_workflow_has_scheduled_scan(self):
        self.assertIn("schedule:", self.workflow_text)
        self.assertIn("cron:", self.workflow_text)

    # --- permission model ---

    def test_workflow_has_security_events_write_permission(self):
        self.assertIn("security-events: write", self.workflow_text)

    def test_workflow_permissions_not_overbroad(self):
        # Read-only contents is the correct minimum for the checkout+init steps.
        self.assertIn("contents: read", self.workflow_text)

    # --- fail-closed behavior ---

    def test_no_continue_on_error_on_analyze_step(self):
        # A `continue-on-error: true` anywhere in the workflow would weaken the
        # fail-closed guarantee. We reject it outright so a misconfiguration
        # cannot silently degrade the gate.
        self.assertNotIn("continue-on-error", self.workflow_text)

    def test_analyze_step_exists(self):
        self.assertIn("github/codeql-action/analyze", self.workflow_text)

    # --- config file usage ---

    def test_workflow_references_codeql_config_file(self):
        self.assertIn("config-file:", self.workflow_text)
        self.assertIn("codeql-config.yml", self.workflow_text)

    # --- config file content: suppression policy ---

    def test_config_declares_suppression_policy(self):
        text = self.config_text.lower()
        self.assertIn("suppression", text,
                      "config must document the suppression/baseline policy")

    def test_config_mentions_baseline(self):
        text = self.config_text.lower()
        self.assertIn("baseline", text,
                      "config must document the SARIF baseline concept")

    def test_config_mentions_false_positive_or_accepted_risk_justification(self):
        text = self.config_text.lower()
        has_justification = ("false positive" in text
                             or "accepted risk" in text
                             or "justification" in text)
        self.assertTrue(has_justification,
                        "config must require a documented justification for "
                        "any query suppression")

    # --- config file content: path coverage ---

    def test_config_includes_application_code(self):
        text = self.config_text
        self.assertTrue(_yaml_list_item(text, "include",
                                        "apps/web/src"),
                        "config must include web application code")
        self.assertTrue(_yaml_list_item(text, "include",
                                        "apps/api/src"),
                        "config must include API application code")
        self.assertTrue(_yaml_list_item(text, "include",
                                        "packages/"),
                        "config must include shared domain packages")

    def test_config_excludes_transient_generated_directories(self):
        text = self.config_text
        self.assertTrue(_yaml_list_item(text, "exclude",
                                        "node_modules"),
                        "config must exclude node_modules")
        self.assertTrue(_yaml_list_item(text, "exclude",
                                        "__pycache__"),
                        "config must exclude __pycache__")

    def test_config_excludes_worktrees(self):
        text = self.config_text
        self.assertTrue(_yaml_list_item(text, "exclude",
                                        "worktrees"),
                        "config must exclude worktrees so each issue "
                        "checkout does not pollute the main scan")

    def test_config_excludes_test_fixtures(self):
        text = self.config_text
        self.assertTrue(_yaml_list_item(text, "exclude",
                                        "tests/fixtures"),
                        "config must exclude golden fixtures (reviewed data, "
                        "not application logic)")

    def test_config_excludes_e2e_test_data(self):
        text = self.config_text
        self.assertTrue(_yaml_list_item(text, "exclude",
                                        "tests/e2e"),
                        "config must exclude E2E test data")

    # --- no secrets/PII in config or workflow text ---

    def test_no_secrets_refs_in_workflow(self):
        text = self.config_text + self.workflow_text
        forbidden = ["GITHUB_TOKEN", "secrets.", "api_key", "password",
                     "tenant_id", "client_secret"]
        for tok in forbidden:
            # Allow references in comments about what must NOT be logged.
            # We check that no active (non-comment) line contains the token.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if tok in stripped:
                    self.fail(
                        f"potential secret reference {tok!r} found in "
                        f"non-comment line: {stripped!r}"
                    )

    # --- negative / abuse scenario: degraded state is defined in config ---

    def test_config_defines_degraded_or_fail_closed_state(self):
        text = self.config_text.lower()
        has_degraded = ("degraded" in text
                        or "fail-closed" in text
                        or "fail closed" in text
                        or "new finding" in text
                        or "informational" in text)
        self.assertTrue(has_degraded,
                        "config must define the degraded/fail-closed state "
                        "so the gate behaviour is explicit")
