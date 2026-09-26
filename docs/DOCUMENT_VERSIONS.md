# DocumentVersion publisher

Issue #536 introduces stable source-document identity and immutable document
version publication.

Identity is defined by `source + document role + source URL`. Re-observing the
same SHA-256 updates only `source_documents.last_seen_at`; the immutable
`document_versions` row is reused. Different bytes under the same identity
create a new DocumentVersion.

The repository stores the RAW snapshot object key, MIME type, size and original
retrieval timestamp. A snapshot from a different source fails closed.

`latest(source_document_id)` resolves the newest immutable version without
overwriting historical versions. This contract is the provenance anchor used by
FieldEvidence (#537) and the atomic canonical publisher (#534).
