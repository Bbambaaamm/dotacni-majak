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

## AdapterContext
Framework poskytuje adapteru sdílené služby:
- `ctx.http` — GuardedHttpClient; adapter nepoužívá vlastní neomezený HTTP client,
- `ctx.snapshots` — RAW snapshot store,
- `ctx.logger`,
- `ctx.budget`,
- `ctx.now`,
- `ctx.run_id`.

MODIFIED source record musí před další pipeline fází odkazovat alespoň na jeden RAW snapshot (`record.snapshot_ids` nebo snapshot vrácený pro artifact). Orchestrator tento invariant vynucuje.

## Adapter NESMÍ
- zapisovat přímo do canonical DB,
- posílat notifications,
- rozhodovat eligibility,
- používat LLM jako source of truth,
- používat neomezený HTTP client,
- obejít RAW-first vrstvu.

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

Redirect target se vždy znovu validuje proti allowlistu a bezpečnosti adresy.

Preferované zdroje: official API → official open data → RSS/Atom → JSON/XML/CSV/XLSX → HTML → PDF/DOCX.

## Checkpoint invariant
Discovery checkpoint se commitne pouze tehdy, když jsou všechny položky dané discovery page úspěšně zpracované. Při částečné chybě zůstává checkpoint beze změny a retry přeskočí již COMPLETED položky.
