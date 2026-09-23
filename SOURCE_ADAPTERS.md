# Source Adapter Contract v1

Každý konektor implementuje čtyři operace:

```python
healthcheck(ctx)
discover(ctx, checkpoint)
fetch_record(ctx, item, validators)
fetch_artifact(ctx, artifact, validators)
```

## Datové kontrakty
- SourceDescriptor
- SourceCheckpoint
- DiscoveryItem
- DiscoveryPage
- RemoteArtifactRef
- NativeRecord
- FetchValidators
- RecordFetchResult
- ArtifactFetchResult
- HealthReport

## Adapter NESMÍ
- zapisovat přímo do canonical DB,
- posílat notifications,
- rozhodovat eligibility,
- používat LLM jako source of truth,
- používat neomezený HTTP client.

## Guarded HTTP Client
Veškeré requesty musí projít centrální vrstvou s:
- host allowlist,
- SSRF protection,
- timeout/redirect policy,
- rate limiting + per-domain concurrency,
- retry/backoff/jitter,
- ETag / If-Modified-Since,
- MIME/size validation,
- SHA-256,
- metrics/logging,
- RAW snapshot integrací.

Preferované zdroje: official API → official open data → RSS/Atom → JSON/XML/CSV/XLSX → HTML → PDF/DOCX.
