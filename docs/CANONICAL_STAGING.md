# Canonical staging repository

Issue #533 adds a fail-closed boundary between normalized source payloads and
immutable canonical publication.

## Invariants

- Staging is not canonical truth.
- One source/external/entity/content-hash tuple is idempotent.
- Changed content creates a distinct staged candidate.
- A candidate cannot become `READY` while provenance is `MISSING`.
- Only `READY` candidates may become `PUBLISHED`.
- Retrying a rejected candidate is explicit and audited through `attempts`.
- Cleanup may remove only terminal `PUBLISHED` / `REJECTED` rows.

## Lifecycle

`STAGED/PENDING → READY/VALID → PUBLISHED`

Validation failure uses `REJECTED/INVALID`. Ambiguous or incomplete input
remains `STAGED/NEEDS_REVIEW`; it is never silently promoted.

The repository stores source-run and ingestion-run references when available,
so a later canonical publisher can retain lineage without reparsing RAW input.
