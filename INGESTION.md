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
