# Live Source Smoke Tests

## Purpose

Regularly verify that connectors still understand **live** official sources,
separated from PR CI to avoid flaky network tests blocking normal development.

This satisfies issue #255 (M3 · Live source smoke-test workflow oddělený od PR CI).

## Design principles

| Principle | How it is enforced |
|---|---|
| **Separated from PR CI** | The `live-smoke.yml` workflow triggers on `workflow_dispatch` + cron only, never on `pull_request`. |
| **Read-only / non-destructive** | Smoke tests perform `healthcheck → discover (page 1) → fetch_record (first item)`. No writes, no artifact downloads. |
| **UNKNOWN ≠ FAIL** | Unexpected errors produce `UNKNOWN` status, distinct from `HEALTHY`, `DEGRADED`, and `UNAVAILABLE`. |
| **Zero-cost-first** | Runs only on GitHub-hosted runners; no paid services or auto-pay. |
| **Rate safety** | Each adapter uses `GuardedHttpClient` with its own `requests_per_second` and `max_concurrency`. |
| **Provenance** | Each result records `adapter_version`, `checked_at`, and `discovered_count`. |
| **Per-source result** | Every source gets its own `SmokeResult` with explicit status. |

## Smoke status states

| Status | Meaning | CI impact |
|---|---|---|
| `HEALTHY` | Full cycle succeeded (healthcheck + discover + fetch_record). | ✅ OK |
| `DEGRADED` | Source responds but partial failure (e.g., zero items on first page, fetch_record returned no record). | ⚠️ Warning |
| `UNAVAILABLE` | Healthcheck explicitly reported `UNAVAILABLE`. | ❌ Blocking |
| `UNKNOWN` | Unexpected error (import failure, network exception, etc.). | ❌ Blocking |

## How to run locally

```bash
# Install dependencies
pip install -e packages/source-sdk
pip install -e 'pipelines/ingestion[documents]'
for d in connectors/*/; do [ -f "${d}pyproject.toml" ] && pip install -e "$d" || true; done

# Run all smoke tests
python3 scripts/live_smoke_runners.py --json

# Run a single source
python3 scripts/live_smoke_runners.py --source EU_FT --json
```

## Alerting policy

- The workflow captures all results (one per source) regardless of individual failures.
- The **aggregate step** fails the job (exit code 1) if any source is `UNAVAILABLE` or `UNKNOWN`.
- `DEGRADED` sources do NOT fail the job but are logged as warnings.
- A JSON artifact (`live-smoke-results.json`) is uploaded for post-run analysis.

## Manifest

The `SMOKE_TARGETS` list in `scripts/live_smoke_runners.py` maps each source code
to its connector adapter. To add a new source:

1. Add a `SmokeTarget(...)` entry to `SMOKE_TARGETS`.
2. Ensure the connector package is installed in CI (auto-discovered via `connectors/*/pyproject.toml`).
3. Ensure there is a smoke script at `scripts/smoke_<source>_connector.py` for manual runs.

## Architecture: why separate from PR CI

Per `ARCHITECTURE.md`, `SOURCE_DEGRADED blokuje destruktivní změny`. Live sources
are volatile — they can return errors, change structure, or be temporarily down.
Running live smoke tests on every PR would cause flaky CI and block valid
changes. Instead:

- **PR CI** (`ci.yml`): tests use fixtures only — no network access to live sources.
- **Live smoke** (`live-smoke.yml`): scheduled daily at 05:00 UTC + manual dispatch.

This keeps PR CI fast, deterministic, and free of external dependencies, while
still regularly validating live-source understanding.
