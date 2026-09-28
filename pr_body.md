## Summary
- **Issue:** #504 — M0 · TypeScript/Python lint, format a type-check toolchain
- **Branch:** `issue-504-lint-toolchain-v2`
- Head SHA: `1af07e5`

**What was done:**
- `ruff.toml` — Python lint + format (rules E, F, I, W, B, C4, UP; E501 ignored)
- `.prettierrc` + `.prettierignore` — TypeScript/JS/MD formatting
- `eslint.config.js` — flat config with `@eslint/js` + `typescript-eslint/recommended`
- `.pre-commit-config.yaml` — hooks for ruff, eslint, prettier
- `package.json` — scripts: lint, lint:fix, format, format:check, lint:py, format:py, format:py:check, lint:all
- `.github/workflows/ci.yml` — CI steps: ESLint, Prettier --check, Ruff check + format-check
- `docs/LINTING.md` — full toolchain documentation
- `tests/python/test_lint_config.py` — 6 config validation tests
- `tests/python/test_lint_error_scenario.py` — 2 error detection tests

## Toolchain versions (reproducible)
| Nástroj | Verze | Kde |
|-----------|-------|------|
| ruff | 0.6.9 | ruff.toml, .pre-commit-config.yaml (rev), CI pip install, docs/LINTING.md |
| eslint | 9.1.0 | CI step (npx --yes eslint@9.1.0), docs/LINTING.md |
| typescript-eslint | 8.10.0 | implied by eslint.config.js usage |
| prettier | 3.3.3 | CI step (npx --yes prettier@3.3.3), docs/LINTING.md |

## Acceptance criteria
- [x] Process is reproducible — config files + documented versions
- [x] CI confirms result — ESLint, Prettier, Ruff in CI foundation job
- [x] Documentation is part of change — docs/LINTING.md
- [x] Error scenario verified — tests/python/test_lint_error_scenario.py demonstrates Ruff detects unused import (F401); documented in docs/LINTING.md
- [x] Security/privacy/a11y — no new credentials, no network calls, no user data accessed

## Files changed
- New: ruff.toml, eslint.config.js, .prettierrc, .prettierignore, .pre-commit-config.yaml
- New: docs/LINTING.md
- New: tests/python/test_lint_config.py
- New: tests/python/test_lint_error_scenario.py
- Modified: package.json (scripts), .github/workflows/ci.yml (CI steps)

## Test plan
- `python3 -m unittest tests/python/test_lint_config tests/python/test_lint_error_scenario` — config validation + error scenario (skips if ruff not installed locally; runs in CI)
- CI: `npm ci && npm run lint && npm run format:check && python3 -m pip install ruff==0.6.9 && ruff check . && ruff format --check .`

Closes #504
