# Connector contract testing

Každý Source Adapter musí být testovatelný bez živého internetu.

## Fixture layout

Doporučená struktura:

```
connectors/<source>/
  fixtures/
    README.md
    listing.*
    detail.*
    document.*
  src/<package>/adapter.py
tests/python/test_<source>_adapter.py
```

Fixtures mají být co nejmenší reprezentativní výřezy skutečného veřejného
kontraktu zdroje. Nesmí obsahovat cookies, tokeny, osobní údaje, neveřejné URL
ani jiné secrets.

Do `fixtures/README.md` uveďte:
- oficiální source URL,
- datum získání fixture,
- co bylo sanitizováno,
- kterou strukturu fixture reprezentuje.

## Standard harness

`dotacni_majak_source_sdk.testing` poskytuje:
- `FixtureHttpClient` — exact-route HTTP bez sítě,
- `FixtureSnapshotStore` — RAW-first in-memory store,
- `make_fixture_context()`,
- descriptor/discovery/record contract assertions,
- `exercise_adapter_contract()`.

Contract suite kontroluje minimálně:
- HTTPS + allowlisted hosts,
- stabilní source code/version,
- discovery ID uniqueness,
- pagination checkpoint invariant,
- MODIFIED record → RAW snapshot,
- source/external identity consistency,
- artifact URL allowlist.

Live smoke test patří do samostatného workflow. Běžné PR CI nesmí být
závislé na dostupnosti externího dotačního portálu.
