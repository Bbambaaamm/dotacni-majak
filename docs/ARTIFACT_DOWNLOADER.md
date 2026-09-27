# Artifact Downloader

## Purpose

Shared conditional downloader for connector document artifacts
(PDFs, HTML pages, XLSX tables, ...). Prevents re-downloading
unchanged documents and always creates an auditable snapshot
reference.

Implements issue [#277](https://github.com/Bbambaaamm/dotacni-majak/issues/277):
*"Znovu nestahovat nezměněné dokumenty a vždy vytvořit auditovatelnou
snapshot vazbu."*

## Architecture

The **adapter** owns the actual HTTP request and RAW snapshot creation.
The **`ArtifactDownloader`** owns validator reuse and the invariant that
HTTP 304 (`NOT_MODIFIED`) can only be accepted when an auditable previous
snapshot exists.

```
adapter.fetch_artifact(ctx, artifact, validators)
        ↓
ArtifactDownloader: look up cached validators (etag, last_modified, sha256)
        ↓
adapter: send conditional request (If-None-Match / If-Modified-Since)
        ↓
adapter returns FetchState.MODIFIED | NOT_MODIFIED | GONE
        ↓
ArtifactDownloader: enforce invariants, update cache, return DownloadedArtifact
```

## Conditional requests

- On first download, no validators are passed (`validators=None`).
- On subsequent downloads, the downloader looks up the cached
  `ArtifactCacheEntry` and builds `FetchValidators(etag=...,
  last_modified=..., known_sha256=...)`.
- The adapter passes these as `If-None-Match` and
  `If-Modified-Since` HTTP headers.
- If the server returns `NOT_MODIFIED`, the downloader reuses the
  cached `snapshot_id` — the document body is never re-transferred.
- The cache key is `(source_code, external_id, url)` so different
  sources or artifacts never collide.

## Invariants (fail-closed)

| Condition | Result |
|---|---|
| `NOT_MODIFIED` without cached `snapshot_id` | `ArtifactInvariantError` |
| `MODIFIED` without `snapshot_id` | `ArtifactInvariantError` |
| MIME type not in allowlist | `ArtifactMimeRejected` |
| `UNKNOWN`/degraded state from adapter | Propagated as exception to caller (orchestrator quarantines) |

`UNKNOWN` and `FAIL` are never conflated: an adapter returning an
unexpected `FetchState` is treated as an error and propagated to the
orchestrator, which may retry or quarantine — never silently accepted.

## MIME policy

`ArtifactDownloadPolicy` validates the MIME type of each downloaded
artifact.

- `allowed_mime_types` — frozenset of allowed MIME types (default includes
  PDF, DOC, DOCX, XLS, XLSX, HTML, plain text, ZIP, and
  `application/octet-stream` as a safe fallback).
- `reject_unknown_mime` — if `True`, `None`/unknown MIME types raise
  `ArtifactMimeRejected` (default: `False`, allowing adapters to handle
  unknown types explicitly).

MIME validation is performed **after** the `MODIFIED` invariant check but
**before** the cache entry is created, so rejected downloads never pollute
the cache.

## Error hierarchy

```
ArtifactDownloadError (RuntimeError)
├── ArtifactInvariantError — protocol/state violations
└── ArtifactMimeRejected  — MIME type not allowed
```

Both subclasses are catchable via the base `ArtifactDownloadError`,
allowing orchestrators to catch artifact-download failures specifically
without swallowing broader adapter errors.

## Snapshot references

- **`ArtifactCacheEntry`** — frozen, slots dataclass storing
  `snapshot_id`, `sha256`, `mime_type`, `size_bytes`, `etag`,
  and `last_modified` per (source, artifact).
- **`DownloadedArtifact`** — result returned to the caller with:
  - `state`: `ArtifactObservedState.MODIFIED | REUSED | GONE`
  - `snapshot_id`: the RAW snapshot reference (or `None` for `GONE`)
  - `previous_snapshot_id`: links the audit chain for `REUSED` and
    `GONE` states

## Zero-cost / performance

- One in-memory `dict` lookup per artifact (cache key: source + external_id + url).
- Validator construction is **O(1)** — three field reads.
- Conditional requests add only HTTP headers (negligible bandwidth).
- Cache is **not persisted** across process restarts; cache warm-up is
  a no-op (first download always sends `validators=None`).
- `download_record_artifacts` iterates artifacts sequentially; parallelisation
  is the caller's responsibility (e.g. `asyncio.gather` of individual `download`
  calls).

## Integration

Adapters call the downloader inside `fetch_record`:

```python
class MyAdapter(SourceAdapter):
    async def fetch_record(self, ctx, item, validators=None):
        # ... fetch the record page, create RAW snapshot ...
        record = NativeRecord(
            source_code=self.descriptor.code,
            external_id=item["id"],
            detail_url=item["url"],
            artifacts=[...],  # RemoteArtifactRef list
        )
        for artifact in self._downloader.download_record_artifacts(
            ctx=ctx, adapter=self, record=record
        ):
            # artifact.state ∈ {MODIFIED, REUSED, GONE}
            # artifact.snapshot_id is the RAW snapshot reference
            record.snapshot_ids.append(artifact.snapshot_id)
        return RecordFetchResult(record=record, ...)
```

The downloader is constructed once per adapter instance:

```python
self._downloader = ArtifactDownloader(cache=cache_repository)
```
