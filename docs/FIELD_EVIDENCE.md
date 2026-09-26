# FieldEvidence persistence

Issue #537 provides the persistence boundary for canonical provenance.

Each evidence record must reference an existing immutable `DocumentVersion`.
An optional `DocumentSection` must also exist. Page ranges are validated before
SQL and database foreign keys remain enabled, so invalid provenance fails
closed instead of being silently stored.

The repository supports idempotent retry by evidence ID and query-by-entity /
query-by-field access for the API and canonical publisher.

Key invariants:

- evidence never points to a missing document version,
- page ranges are either both absent or valid with `page_from >= 1` and
  `page_to >= page_from`,
- confidence is stored deterministically as parts-per-million,
- verification status is restricted to the canonical enum,
- deleting a referenced DocumentVersion is blocked,
- deleting an optional section nulls only the section reference, preserving the
  evidence row and immutable document version link.

This repository is consumed by the atomic canonical publisher (#534) and the
detail/provenance E2E path (#572/#508).
