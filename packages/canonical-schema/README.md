# Canonical schema package

## Jediný source of truth
Canonical datové kontrakty jsou definovány výhradně v:

`schemas/v1/*.schema.json`

TypeScript a Python modely se **negenerují ručně**.

## Generování

```bash
python3 scripts/generate_contracts.py
```

Výstup:
- `generated/types.ts`
- `generated/models.py`
- `generated/manifest.json`

Adresář `generated/` je build artefakt a není verzovaný v Gitu. Tím nemohou vzniknout dva ručně udržované modely, které se postupně rozjedou.

## CI
CI generuje kontrakty do dočasného adresáře, ověří determinismus, úplnost manifestu a import Pydantic modelů.

## Přesnost
JSON Schema zůstává runtime validační autorita. Generated Pydantic/TypeScript modely jsou ergonomická reprezentace stejného kontraktu.
