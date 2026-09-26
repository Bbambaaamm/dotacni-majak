# SourceRecord change detection

Issue #535 moves stable source-record identity and hash comparison into a
persistent repository that can run before expensive parsing/publication.

## Observation result

- `NEW` — the `(source, external_id)` identity was not seen before.
- `NOT_MODIFIED` — the same identity has the same SHA-256 content hash.
- `CHANGED` — the stable identity exists but upstream content changed.

Every successful observation updates `last_seen_at` and resets source
presence to `SEEN / missing_run_count=0`. It deliberately does **not** mutate
`grant_calls.current_status`; disappearance/cancellation remains a separate
verified decision.

An existing canonical grant link is retained when a later observation does not
supply a replacement. Database foreign keys guard explicit links.

This repository is intended to feed the staging/publisher path so unchanged
records can skip expensive parsing while changed records create new immutable
canonical/document versions.
