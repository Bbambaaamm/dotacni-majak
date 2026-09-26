# Atomic canonical publisher

Issue #534 closes the trust boundary between validated staging and public
canonical data.

The publisher accepts only a VALID + READY staged GRANT_CALL candidate whose
provenance is not MISSING and whose content hash matches the latest observed
SourceRecord.

A single SQLite/D1-compatible transaction performs:

1. stable GrantCall identity validation/creation,
2. immutable GrantCallVersion creation (deduplicated by call + content hash),
3. FieldEvidence persistence against immutable DocumentVersion rows,
4. current-version pointer/status/title update,
5. SourceRecord → GrantCall linkage,
6. SEARCH_REINDEX_REQUIRED and CHANGE_DETECTION_REQUIRED outbox enqueue,
7. staging transition READY → PUBLISHED.

Any failure rolls back all seven steps. The staged candidate remains READY and
can be retried. Retrying an already published candidate is idempotent and
returns the existing immutable version.

The staged payload contract for this publisher contains programme_id,
canonical_slug, title, status, verification_status and optional canonical
version fields. Evidence entries use the FieldEvidence contract fields
field_path, document_version_id, verification_status and optional section/page/
text/extractor/confidence metadata.
