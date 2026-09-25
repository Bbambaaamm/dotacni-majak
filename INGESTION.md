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

### Persistent quarantine review/reprocess

`SqliteQuarantineRepository` uchovává unresolved queue v D1-kompatibilním SQLite
schématu včetně vazby na source identity a RAW `payload_ref`.

Reprocess není implicitní retry canonical publish. Je to explicitní auditovaná akce:
1. vytvoří `quarantine_reprocess_attempts` záznam,
2. zpracuje stejný RAW payload novou/opravnou verzí parseru,
3. při chybě ponechá quarantine item otevřený,
4. teprve po úspěchu označí attempt SUCCEEDED a item jako resolved.

Tím lze opravit parser a bezpečně znovu zpracovat problematická data bez nového
stahování a bez ztráty audit trailu.
