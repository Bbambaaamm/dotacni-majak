## Residual risks (not blockers for this slice)
- CodeQL is static analysis: it does not cover runtime abuse, business logic vulns,
  za-running attacks, or SSRF/IDOR that only manifests at runtime.
- SARIF baseline for accepted findings is NOT created in this slice — the first
  successful CodeQL run on main will produce it, and that run must be reviewed
  before prod. Until then, ANY finding in scope fails the PR (fail-closed).
- `pip-audit` in `dependency-audit.yml` already covers dependency vulns; this slice
  does not change that workflow.
- CodeQL analysis can be slow and can be re-run manually — the workflow is
  scheduled weekly, but a PR may need a re-run if caching false-fails.
- CodeQL does not run typecheck or unit tests; those remain in `ci.yml`.
