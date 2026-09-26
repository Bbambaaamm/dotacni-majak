# Structured JSON / XML Parsing

Issue #238 implements a deterministic, schema-neutral parsing layer for API
and open-data payloads.

## JSON

- input must be UTF-8,
- duplicate object keys are rejected,
- NaN / Infinity values are rejected,
- object keys are walked in sorted order,
- provenance uses RFC-6901-style JSON Pointer paths,
- canonical text uses sorted compact JSON serialization.

Examples:

- `/calls/0/deadline`
- property `a/b` → `/a~1b`
- property `x~y` → `/x~0y`

## XML

XML passes the document-security DTD/entity preflight and is then parsed with
defusedxml.

Provenance paths include repeated sibling indexes:

- `/calls[1]/call[1]/@id`
- `/calls[1]/call[2]/deadline[1]/#text`

Attributes, element text and significant tail text are preserved. Canonical
text uses Python XML C14N 2.0 serialization.

## Limits

Both formats enforce:
- input bytes,
- node count,
- nesting depth,
- scalar length,
- total scalar text.

XML additionally limits attributes per element.

This layer does **not** infer grant semantics or mutate canonical entities.
Structured extraction happens later and must retain these field paths as
evidence anchors.
