# Source Fixture Policy

Connector fixtures are stable test inputs, **not** the RAW production archive.

## Required manifest

A connector whose fixtures are managed under this policy has:

`connectors/<connector>/fixtures/manifest.json`

Every local fixture must be listed with:

- official `sourceUrl`,
- UTC `capturedAt`,
- MIME type,
- SHA-256,
- origin type,
- explicit PII review status,
- sanitization status.

CI validates that:
- the manifest lists every fixture file exactly once,
- no path escapes the fixture directory,
- URLs are HTTPS and contain no credentials,
- fixture size stays bounded,
- common secret patterns are absent,
- SHA-256 matches the committed bytes.

## Origin types

### SANITIZED_DERIVATIVE
A minimized/sanitized representation derived from an official public response.
It preserves the fields/HTML structure needed by contract tests, but is not
claimed to be a byte-identical upstream snapshot.

### GENERATED
A project-created parser/security fixture with no claim of official origin.
Generated fixtures should normally live in generic test fixtures rather than
connector source fixtures.

## Personal data

Allowed reviewed states:
- `NONE_OBSERVED`
- `PUBLIC_CONTACTS_REMOVED`
- `REDACTED`

There is intentionally no `UNKNOWN`/unchecked state accepted by CI.

## Binary official documents

Do **not** commit third-party PDF/DOCX/XLSX originals to the open-source
repository merely because they are publicly downloadable.

Unless redistribution is explicitly reviewed, production binaries remain:
- referenced by their official URL,
- captured as RAW snapshots in runtime storage,
- validated by live smoke/source-health workflows.

Parser unit tests use project-generated minimal binary documents.

## Updating a source fixture

1. Fetch through the connector/GuardedHttpClient or an approved research path.
2. Minimize to the smallest structure that exercises the contract.
3. Remove personal/public-contact data not necessary for the test.
4. Set `capturedAt`, source URL, MIME, PII and sanitization fields.
5. Compute the new SHA-256.
6. Run `python3 scripts/validate_source_fixtures.py`.
7. Review connector fixture tests and any semantic contract change.

A changed hash without an accompanying manifest review is a CI failure.
