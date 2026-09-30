## Tests run
- `tests/python/test_sast_workflow_contract.py` — 20 tests, OK
- `tests/python/test_v1_release_gate_contract.py` — 3 tests, OK (no regression)

## What the test validates
- workflow triggers on push/PR/schedule to main
- workflow has security-events: write + contents: read
- workflow references config file, no continue-on-error
- config exists, declares suppression policy + baseline
- config includes application code, excludes transients/worktrees/fixtures/E2E
- no secret references in non-comment lines
- config defines degraded/fail-closed state
