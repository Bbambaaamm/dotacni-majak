# Ingestion Pipeline

```
SCHEDULE
→ LOCK
→ HEALTH CHECK
→ DISCOVER
→ FETCH
→ RAW SNAPSHOT
→ HASH
→ PARSE
→ SEGMENT
→ EXTRACT
→ NORMALIZE
→ VALIDATE
→ ENTITY RESOLUTION
→ STAGE
→ PUBLISH
→ FTS INDEX
→ SEARCH PROFILE
→ VECTOR INDEX
→ CHANGE DETECTION
→ WATCH MATCHING
→ NOTIFICATION OUTBOX
```

## Item states
DISCOVERED → FETCHING → FETCHED → SNAPSHOTTED → PARSED → EXTRACTED → NORMALIZED → VALIDATED → STAGED → PUBLISHED → INDEXED → COMPLETED.

Chyby: RETRYABLE_FAILED / QUARANTINED / PERMANENT_FAILED.

## Povinné vlastnosti
- Každý krok idempotentní.
- RAW snapshot nikdy nepřeskakovat.
- Reprocess novou verzí parseru bez nového downloadu.
- Publish až po validation gate.
- Indexy/notifikace přes retryable outbox.
- Discovery checkpoint se posouvá až po úspěšném zpracování celé stránky.

## Run-level Data Quality Gate

Po dokončení discovery se kvalita běhu posuzuje proti rolling baseline a interním metrikám:
- počet nalezených záznamů,
- HTTP error rate,
- parse success rate,
- validation success rate,
- neočekávaná změna struktury zdroje.

Příklad:

```
běžně 118–122 výzev
aktuální run 0 výzev
→ SOURCE DEGRADED
→ destructive_changes_allowed = false
```

**Degradovaný run nesmí provést destruktivní reconciliation** — tedy hromadně uzavřít, zrušit nebo odstranit poslední známé canonical záznamy jen proto, že aktuální parser nic nenašel.

Bezpečné nové/aktualizované záznamy mohou být zpracovány, pokud samy projdou validation/provenance gates. Podezřelé payloady se ukládají do quarantine a předchozí publikovaná verze zůstává last-known-good.

## Quarantine

Quarantine je oddělená od canonical publikace. Používá se minimálně pro:
- validation/schema failure,
- quality-gate problém,
- nejednoznačnou duplicitu,
- security rejection,
- další případy vyžadující review.

Quarantine item musí nést source/external identity, důvod a pokud možno odkaz na RAW payload.

## Transactional Outbox

Canonical změna a odpovídající outbox event musí být vloženy **ve stejné databázové transakci**.

Typické eventy:
- SEARCH_REINDEX_REQUIRED
- VECTOR_REINDEX_REQUIRED
- CHANGE_DETECTION_REQUIRED
- WATCH_REEVALUATION_REQUIRED
- NOTIFICATION_REQUIRED

`dedupe_key` je unikátní. Consumer používá at-least-once delivery a idempotentní handler. Selhání Vectorize nebo notification providera proto neztratí canonical update; event zůstane PENDING/FAILED k retry.

## Disappearance safety

SEEN → MISSING_CANDIDATE → CONFIRMED_MISSING.

CONFIRMED_MISSING pouze znamená, že záznam už na zdroji není vidět. Neznamená automaticky CLOSED/CANCELLED.

Canonical status CLOSED/CANCELLED vzniká pouze z autoritativního důkazu.

## Source run quality gate

Výrazný propad počtu záznamů, vysoká chybovost nebo změna struktury zdroje → DEGRADED a blokace destruktivních změn.

Poslední ověřená data zůstávají publikovaná a Source Health musí umět uživateli ukázat stáří posledního úspěšného běhu.


## Persistent run state and source leases

Produkční ingestion nespoléhá na process memory. Migration `0020_ingestion_runtime.sql`
přidává:
- `source_checkpoints` — restartovatelný discovery cursor/state,
- `ingestion_runs` — audit každého pokusu a jeho výsledku,
- `ingestion_items` — idempotence/retry stav v rámci konkrétního runu,
- `ingestion_locks` — lease proti paralelnímu zpracování stejného zdroje.

### Lease invariant
Před health/discovery musí běh získat source lease. Po úspěšném zpracování stránky
se lease obnovuje **před** posunem checkpointu. Pokud lease nelze obnovit,
běh se zastaví a checkpoint se neposune.

### Run-scoped idempotence
Stav `COMPLETED` znamená „tato source identity je hotová v tomto runu“, ne
„už ji nikdy nekontroluj“. V novém runu se položka vrací na `DISCOVERED`,
aby mohla zachytit změněný upstream obsah a vytvořit novou immutable verzi.

`SqliteIngestionRepository` je referenční implementace nad D1-kompatibilním
SQLite SQL. Heavy ingestion běží mimo Worker; jiný D1 transport musí zachovat
stejný repository contract a transakční invarianty.


## Persistent transactional outbox worker

`SqliteOutboxRepository` je referenční D1-kompatibilní implementace
produkčního outbox kontraktu.

### Atomic enqueue
Canonical write a outbox event musí být součást stejné DB transakce.
`enqueue(..., commit=False)` umožňuje callerovi vložit event do již otevřené
transakce a commitnout canonical změnu + event společně.

### Claim lease
Worker vybírá jen:
- PENDING/FAILED event s `available_at <= now`,
- nebo PROCESSING event, jehož lease expiroval.

Claim nastaví `PROCESSING`, zvýší `attempts` a přidělí časově omezený lease
konkrétnímu workeru. Jiný worker nesmí event dokončit bez aktivního lease.

### Retry a dead-letter
Selhání handleru:
1. uvolní lease,
2. uloží chybu,
3. naplánuje další `available_at` podle backoff policy,
4. po dosažení max attempts nastaví `dead_lettered_at`.

Dead-letter event zůstává auditovatelný v databázi, ale není znovu claimován.

### At-least-once semantics
Handler může být po expiraci lease spuštěn znovu, proto musí být idempotentní
podle `event.id`, `dedupe_key` nebo idempotency key cílové služby.
`OutboxWorker` označí event DELIVERED až po úspěšném návratu handleru.

### Observability
Repository poskytuje základní queue metrics:
PENDING, PROCESSING, FAILED, DELIVERED, DEAD_LETTER a aktuálně READY.


## Presence reconciliation

Po úspěšném discovery běhu se source identities porovnají s per-source seznamem
`seen_external_ids`.

Přechody:
- `SEEN → MISSING_CANDIDATE`
- `MISSING_CANDIDATE → CONFIRMED_MISSING` až po konfigurovatelném počtu úspěšných běhů
- znovu nalezený záznam se vždy vrací na `SEEN` a missing counter se resetuje.

Pokud quality gate vrátí `destructive_changes_allowed=false`, presence reconciler
**nesmí** posunout žádný missing counter ani stav. Tím se rozbitý parser nemůže
proměnit v hromadné „zmizení“ výzev.

`CONFIRMED_MISSING` je pouze stav source recordu. Presence reconciler nikdy
nemění `grant_calls.current_status`; CLOSED/CANCELLED smí vzniknout jen z
autoritativního důkazu ve verzi výzvy.

