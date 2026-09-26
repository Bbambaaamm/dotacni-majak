# First trusted connector E2E

Issue #572 proves that the first two distinct official retrieval paths can
traverse the trusted backend rather than the legacy direct local publisher.

Path under test:

official connector fixture -> RAW snapshot -> normalizer -> SourceRecord
change detection -> immutable DocumentVersion -> canonical staging -> atomic
GrantCallVersion + FieldEvidence + outbox -> search projection/FTS.

The deterministic integration test uses the real NSA HTML connector and the
real EU Funding & Tenders JSON/API connector with their checked-in sanitized
official-contract fixtures. No live website is required in PR CI.

Important semantics:

- NSA fixture 16/2026 is CLOSED and is still indexed for audit/history, but the
  public search API correctly excludes it from active OPEN/PLANNED/ANNOUNCED
  results.
- EU Funding fixture is OPEN and remains searchable.
- Search projection consumes SEARCH_REINDEX_REQUIRED idempotently.
- The source-record RAW snapshot is the provenance anchor for title/status/
  summary/deadline in this first end-to-end proof.
- Official binary call documents remain a separate artifact path; their
  immutable DocumentVersion support is already provided by #536.
