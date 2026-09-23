# Architecture

## Cíl
Dotační maják je auditovatelný dotační radar konkrétních záměrů. Data nikdy nejdou přímo ze zdroje k uživateli.

```
OFFICIAL SOURCES
      ↓
Source Adapters
      ↓
RAW snapshots (R2)
      ↓
Parse → Extract → Normalize → Validate
      ↓
Canonical GrantCallVersion (D1)
      ↓
FTS / SearchProfile / Vector index
      ↓
Eligibility + Finance + Explainability
      ↓
API
      ↓
PWA
```

Paralelně:

```
new document/version
      ↓
Change detector
      ↓
ChangeEvent
      ↓
Watch matcher
      ↓
Notification outbox
```

## Hranice modulů

- **Source Adapter** pouze objevuje/stahuje data a dokumenty.
- **Ingestion** ukládá RAW, parsuje, normalizuje, validuje a publikuje.
- **Canonical schema** je jediný interní datový kontrakt.
- **Search** určuje tematickou relevanci.
- **Eligibility** deterministicky vyhodnocuje podmínky.
- **Finance** deterministicky počítá financování.
- **AI** může navrhovat klasifikaci/extrakci, ale není source of truth.
- **UI** vždy vysvětluje proč se výzva zobrazila a co má uživatel udělat dál.

## Klíčová bezpečnostní pravidla

- RAW-first.
- Immutable GrantCallVersion a DocumentVersion.
- Provenance na důležitých polích.
- Žádný arbitrary eval v rules DSL.
- Zmizení z listingu ≠ CANCELLED.
- SOURCE_DEGRADED blokuje destruktivní změny.
- Vedlejší indexy a notifikace přes retryable outbox.
- Zero-cost fallback: semantic search může degradovat na FTS + ontologii + filtry.

## Search
Intent normalization → ontology expansion → lexical retrieval → semantic retrieval → structured filters → eligibility → finance compatibility → explainability.

**Relevance, eligibility, finance match a readiness jsou čtyři oddělené výsledky.**
