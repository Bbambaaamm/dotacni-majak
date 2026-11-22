# Security — Dotační maják

## Overview
Dotační maják is a public open-source service. Security posture focuses on:
- supply-chain integrity of CI/CD (this document),
- data provenance and deterministic processing (see ARCHITECTURE.md, DATA_MODEL.md),
- source-adapter sandboxing (see SOURCE_ADAPTERS.md),
- document ingestion safety (see docs/DOCUMENT_SECURITY.md if present, or issue #61),
- privacy (see issue #431 privacy inventory).

## GitHub Actions supply-chain policy

### Pinning rules
- **Third-party actions** (any `uses:` not from `actions/` or `github/` org):
  MUST be pinned by full 40-char commit SHA. Floating tags (`@v4`, `@main`,
  `@branch`) are prohibited because a compromised tag can redirect execution.
- **First-party GitHub actions** (`actions/*`, `github/*`):
  MUST use a MAJOR version tag (`@v7`, `@v4`, …). `@main`, `@branch`,
  or unversioned refs are prohibited.
- **Enterprise/validation actions** we author ourselves follow the same
  SHA-pin rule once they leave draft.

### Permissions
- Default workflow `permissions:` is `contents: read`.
- Only two exceptions are allowed:
  - `security-events: write` — CodeQL workflow (required by CodeQL action).
  - `contents: write` — release-gate workflows that produce tagged releases
    (`v1-release-gate.yml`, `beta-gate.yml`). These are dispatch-only and
    never run on PRs from forks.
- Any other permission key (`id-token`, `packages`, `deployments`, …) is a
  review-required deviation and must be justified in the PR.

### Secrets in workflows
- No workflow-level `env:` block may define secret-like variables.
- Secrets are referenced only at step level via `${{ secrets.NAME }}` and
  never printed to logs (no `echo ${{ secrets.X }}`).
- Fork PRs must not receive any repository secret. Workflows that need
  secrets must use `pull_request_target` with explicit review or run only
  on `push` / `workflow_dispatch` / `schedule`.

### Negative / abuse scenarios covered
- **Compromised tag**: SHA pinning means a replaced tag does not redirect CI.
- **Over-broad token**: `contents: read` default + allowlist prevents
  accidental write/delete on PRs.
- **Secret exfiltration via log**: no workflow-level secret env; step-level
  secrets are not echoed.
- **Fork PR privilege escalation**: no `pull_request_target` with secrets;
  live smoke and probes are dispatch/schedule-only, not PR-triggered.

### Fail-closed / degraded
- The `scripts/verify_actions.py` checker runs on every PR and push to main.
  Any pinning or permissions violation **fails the CI job** (exit 1).
- When a pinned action SHA no longer exists (repo deleted, tag moved), the
  workflow **fails Closed** — the job errors, no compromise executes. The
  fix is to update the SHA to the new pinned commit in a reviewable PR.
- Live smoke workflows (`live-smoke.yml` and per-source probes) are
  **separated from PR CI** (see docs/LIVE_SMOKE.md) to avoid network flakiness
  blocking development and to limit the blast radius of any CI credential issue.

## Review policy
- Any change to `.github/workflows/*.yml` requires at least one reviewer
  familiar with the supply-chain policy above.
- New third-party actions require explicit justification in the PR description
  (why this action, why this version/SHA, what permissions it needs).
- The security checklist item in `PULL_REQUEST_TEMPLATE.md` must be completed.

## Updating pinned SHAs
When a pinned action releases a new version:
1. Find the new tagged commit SHA (e.g. `gh api repos/OWNER/REPO/git/refs/tags/vN`).
2. Open a PR updating only the SHA in the affected workflow file.
3. The PR title should reference the action and new version.
4. CI must pass (including `verify_actions.py` itself — it uses only stdlib).

## CI verification
`scripts/verify_actions.py` is the automated enforcement point. It scans
all `.github/workflows/*.yml` and fails on:
- third-party actions not pinned by SHA,
- first-party actions not using a major version tag,
- workflow permissions outside the allowed minimal set,
- workflow-level env keys that look like secrets.

Run locally: `python3 scripts/verify_actions.py`

## Residual risks (documented, not yet mitigated)
- **Docker container actions**: actions that run as Docker containers are
  pinned by SHA at the action level, but the container image inside may be
  mutable if the action uses `docker://` with a tag. We avoid such actions.
- **GitHub-hosted runner compromise**: we rely on GitHub's runner security;
  no self-hosted runners are used, so no org-controlled host attack surface.
- **`actions/checkout` credential exposure**: `actions/checkout@v7` receives
  `GITHUB_TOKEN` with `contents: read`. This is the minimum required for
  checkout; no elevated token is passed.
- **Dependency audit tooling**: `dependency-audit.yml` runs `npm audit` and
  `pip-audit`. These detect known vulns in declared dependencies but not in
  transitive unresolved or post-install scripts. See issue #211 for the
  rationale and gap discussion.

## References
- Issue #429 — this policy document's parent issue.
- Issue #211 — Actions runtime modernization (dependency review, CodeQL).
- `docs/LIVE_SMOKE.md` — why live smoke is separated from PR CI.
- `scripts/verify_actions.py` — automated enforcement.
