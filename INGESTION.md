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
- Publish až po quality gate.
- Indexy/notifikace přes retryable outbox.

## Disappearance safety
SEEN → MISSING_CANDIDATE → CONFIRMED_MISSING.

CONFIRMED_MISSING pouze znamená, že záznam už na zdroji není vidět. Neznamená automaticky CLOSED/CANCELLED.

## Source run quality gate
Výrazný pokles počtu záznamů, parse success nebo změna struktury zdroje → SOURCE_DEGRADED a blokace destruktivních změn.


## Data quality gate

Po dokončení source run se vyhodnocují signály kvality proti rolling baseline:

- výrazný propad počtu nalezených záznamů,
- HTTP error rate,
- parse success rate,
- validation success rate,
- neočekávaná strukturální změna zdroje.

Výsledek je `HEALTHY` nebo `DEGRADED`.

### Kritický invariant
`DEGRADED` run může přinést nové nedestruktivní informace, ale **nesmí být použit k hromadnému uzavření, zrušení nebo smazání posledních důvěryhodných canonical záznamů**.

První prázdný run bez historické baseline se automaticky nepovažuje za rozbitý zdroj; teprve stabilní baseline dovoluje detekovat kolaps typu 120 → 0.

## Quarantine

Nová data, která neprojdou schema/validation/security/duplicate gate, se nepřepisují přes poslední publikovanou verzi. Jsou uložena do `quarantine_items` s explicitním důvodem a zůstávají tam do vědomého vyřešení.

## Transactional outbox

Vedlejší práce po canonical publish se reprezentuje outbox událostmi:

- `SEARCH_REINDEX_REQUIRED`
- `VECTOR_REINDEX_REQUIRED`
- `CHANGE_DETECTION_REQUIRED`
- `WATCH_REEVALUATION_REQUIRED`
- `NOTIFICATION_REQUIRED`

`dedupe_key` je unikátní idempotency guard. Persistentní D1 implementace musí canonical write a příslušný outbox event uložit v jedné databázové transakci; selhání workeru nesmí událost ztratit.
