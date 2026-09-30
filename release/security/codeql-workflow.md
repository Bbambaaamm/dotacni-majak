## Files
- `.github/workflows/codeql.yml`
- `.github/codeql-config.yml`

## Lineage
Worktree root commit: `git rev-parse HEAD` in this worktree.

## What changed
- Created `.github/codeql-config.yml` (scope + exclusions + suppression policy).
- Updated `.github/workflows/codeql.yml` to use `config-file: ./.github/codeql-config.yml` and removed inline `queries: security-extended`.
- Added `tests/python/test_sast_workflow_contract.py`.
- Added `security_sast_scan_acceptable` to `release/v1-gate.json automated`.
- Added `docs/adr/0007-codeql-sast-baseline.md`.
- Updated `docs/V1_RELEASE_GATE.md` (new CodeQL SAST gate section).
- Updated `SECURITY.md` (SAST workflow section).
