PRAGMA foreign_keys = ON;

-- Persistent rolling baseline per source, consumed by the data quality gate and
-- Source Health. One row per source is upserted (idempotently) after each source
-- run. `median_records` and the rate columns are NULL while the baseline is still
-- bootstrapped (too few same-version runs), which the quality gate treats as
-- "no baseline yet" rather than "broken".
CREATE TABLE source_run_baselines (
  source_id TEXT PRIMARY KEY
    REFERENCES source_registry(id) ON DELETE CASCADE,
  adapter_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
  median_records REAL CHECK (median_records IS NULL OR median_records >= 0),
  mean_error_rate REAL CHECK (mean_error_rate IS NULL OR (mean_error_rate >= 0 AND mean_error_rate <= 1)),
  mean_success_rate REAL CHECK (mean_success_rate IS NULL OR (mean_success_rate >= 0 AND mean_success_rate <= 1)),
  is_bootstrapped INTEGER NOT NULL DEFAULT 1 CHECK (is_bootstrapped IN (0,1)),
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_source_run_baselines_version
  ON source_run_baselines(adapter_version);
CREATE INDEX idx_source_run_baselines_updated
  ON source_run_baselines(updated_at);

-- Supports the rolling-window lookup over finished, same-version source runs.
-- LOCKED rows are skipped by the repository (they are lock-miss attempts, not
-- real source observations) and unfinished runs are excluded so an in-flight
-- run never pollutes a baseline it did not complete.
CREATE INDEX idx_source_runs_baseline_lookup
  ON source_runs(source_id, adapter_version, status, started_at DESC);
