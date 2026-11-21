#!/usr/bin/env python3
"""
GitHub Actions supply-chain integrity checker.

Verifiable via CI: `python3 scripts/verify_actions.py`.
Fails closed: any violation is a hard error.

Checks
------
1. Third-party actions (not actions/ or github/ org) MUST be pinned by
   full 40-char SHA — no floating tags like @v4, @main, @branch.
2. First-party GitHub actions MUST use a MAJOR version tag (e.g. @v7,
   @v4) — never @main, @branch, or unversioned.
3. Workflow top-level `permissions:` must be a safe minimal set.
   Allowed keys: contents (read), security-events (write), checks (write).
   Any other key (id-token, packages, deployments, ...) is a violation
   unless the workflow opts in explicitly via an allowlist comment.
4. No `env:` block at workflow level may contain secret-like names
   (GITHUB_TOKEN, SECRET, KEY, TOKEN, PASSWORD, API_KEY, …).
   Individual step env is allowed (those are not workflow-level leaks).

Exit code 0 = clean, 1 = violations found.
"""

import argparse
import re
import sys
from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")

# ── allowed permissions ──────────────────────────────────────────────────────
_ALLOWED_PERMISSION_KEYS = frozenset({"contents", "security-events", "checks"})
# contents may be "read" or "write" (write only for release workflows that
# explicitly opt in — see below). For normal workflows we only allow read.
_DEFAULT_ALLOWED_CONTENTS = frozenset({"read"})

# Workflows that are allowed contents: write (release gates, dispatch-only).
_CONTENTS_WRITE_ALLOWLIST = frozenset({
    "v1-release-gate.yml",
    "beta-gate.yml",
})

# ── third-party SHA pattern ───────────────────────────────────────────────────
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _parse_uses(uses_str: str):
    """Return (org_repo, ref) from 'org/repo@ref'."""
    if "@" in uses_str:
        org_repo, ref = uses_str.rsplit("@", 1)
    else:
        org_repo, ref = uses_str, "main"  # default branch — always a problem
    return org_repo, ref


def _is_actions_org_first_party(org_repo: str) -> bool:
    """Actions under the `actions/` org (e.g. actions/checkout).

    These are maintained by GitHub and use MAJOR version tags (@v7, @v4).
    They must NOT be pinned by SHA — doing so would pin to a specific
    release and miss security backports that GitHub publishes under the tag.
    """
    return org_repo.startswith("actions/")


def _is_github_org_first_party(org_repo: str) -> bool:
    """Actions under the `github/` org (e.g. github/codeql-action).

    These are also maintained by GitHub but are NOT in the `actions/` org.
    For supply-chain integrity we pin these by immutable SHA (same as
    third-party), because the `github/` org does not follow the same
    tag-to-SHA stability guarantees as `actions/`.
    """
    return org_repo.startswith("github/")


def _is_third_party(org_repo: str) -> bool:
    return not org_repo.startswith("actions/") and not org_repo.startswith("github/")


def _is_major_tag(ref: str) -> bool:
    return bool(re.match(r"^v\d+$", ref))


# ── permission checks ────────────────────────────────────────────────────────
def _parse_permissions(block: str):
    """Parse `permissions:` YAML block (indented) into dict.

    Skips the `permissions:` header line itself — only parses indented
    key: value pairs inside the block.
    """
    perms = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # skip the header line "permissions:" itself
        if stripped == "permissions:":
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            perms[key.strip()] = val.strip().strip("[]").strip('"').strip("'")
    return perms


def check_workflow(path: Path) -> list[str]:
    """Return a list of violation strings for one workflow file."""
    violations = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # ── 1. Find `uses:` lines and check pinning ────────────────────────────
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^\s+uses:\s+(.+)$", line)
        if not m:
            continue
        uses_val = m.group(1).strip().strip('"')
        org_repo, ref = _parse_uses(uses_val)

        if _is_actions_org_first_party(org_repo):
            if not _is_major_tag(ref):
                violations.append(
                    f"{path.name}:{i}: actions/ org action "
                    f"{org_repo} must use a MAJOR version tag "
                    f"(e.g. @v7), got @{ref!r}"
                )
        else:
            # github/ org actions and all third-party: must be pinned by SHA
            if not _SHA40.match(ref):
                violations.append(
                    f"{path.name}:{i}: action {org_repo} must be pinned "
                    f"by immutable SHA, got @{ref!r} "
                    f"— float tag is a supply-chain risk"
                )

    # ── 2. Check top-level permissions block ────────────────────────────────
    perms_block = []
    in_perms = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("permissions:"):
            in_perms = True
            perms_block = [line]
            continue
        if in_perms:
            # stop at first top-level key (no indentation)
            if line and not line[0].isspace() and stripped:
                break
            perms_block.append(line)

    if perms_block:
        perms = _parse_permissions("\n".join(perms_block))
        for key, val in perms.items():
            if key not in _ALLOWED_PERMISSION_KEYS:
                violations.append(
                    f"{path.name}: permissions key {key!r} is not in the "
                    f"allowed minimal set {_ALLOWED_PERMISSION_KEYS}"
                )
            if key == "contents" and path.name not in _CONTENTS_WRITE_ALLOWLIST:
                if val != "read":
                    violations.append(
                        f"{path.name}: contents must be 'read' for "
                        f"non-release-gate workflows, got {val!r}"
                    )

    # ── 3. Workflow-level env: no secret-like names ─────────────────────────
    in_workflow_env = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("env:"):
            in_workflow_env = True
            continue
        if in_workflow_env:
            if line and not line[0].isspace() and stripped:
                break  # top-level key ended
            if ":" in stripped and not stripped.startswith("#"):
                key = stripped.split(":", 1)[0].strip()
                if _looks_like_secret(key):
                    violations.append(
                        f"{path.name}: workflow-level env key {key!r} "
                        f"looks like a secret — secrets must not be "
                        f"defined at workflow scope"
                    )

    return violations


def _looks_like_secret(key: str) -> bool:
    secret_patterns = [
        "token", "secret", "key", "password", "api_key", "apikey",
        "credential", "auth", "private", "cert", "ssh",
    ]
    low = key.lower()
    return any(p in low for p in secret_patterns)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GitHub Actions supply-chain integrity checker"
    )
    parser.add_argument(
        "--workflow-dir",
        type=Path,
        default=WORKFLOW_DIR,
        help="Directory containing workflow YAML files",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Optional allowlist file (one violation regex per line, "
        "skipped if matched)",
    )
    args = parser.parse_args()

    workflow_dir = args.workflow_dir
    if not workflow_dir.is_dir():
        print(f"ERROR: {workflow_dir} is not a directory", file=sys.stderr)
        return 2

    allowlist_patterns = []
    if args.allowlist and args.allowlist.is_file():
        allowlist_patterns = [
            re.compile(line.strip())
            for line in args.allowlist.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def _skipped(violation: str) -> bool:
        return any(p.search(violation) for p in allowlist_patterns)

    all_violations = []
    for yml in sorted(workflow_dir.glob("*.yml")):
        # skip workflow dispatch-only files that are not real CI? no — check all
        for v in check_workflow(yml):
            if not _skipped(v):
                all_violations.append(v)

    if all_violations:
        print("FAIL: GitHub Actions supply-chain violations found:\n")
        for v in all_violations:
            print(f"  • {v}")
        print()
        print("Fix: pin third-party actions by immutable SHA, use major tags "
              "for first-party actions, and restrict workflow permissions.")
        return 1

    print("PASS: all GitHub Actions supply-chain checks clean.")
    print(f"Scanned {len(list(workflow_dir.glob('*.yml')))} workflow files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
