# D1 / SQLite migrations

Migrace jsou aplikovány v lexikografickém pořadí a nesmí být po merge přepisovány. Každá změna schématu dostane novou migration.

## Finanční reprezentace
Peníze se v databázi ukládají jako **integer minor units** (např. haléře/centy), nikoliv floating point.

Příklad:
- 4 000 000,00 Kč → `400000000` minor units.

Procenta podpory/spoluúčasti se ukládají jako **basis points**:
- 90 % → `9000`
- 12,5 % → `1250`

Tím se vyhneme chybám binárního floating pointu v kritických finančních výpočtech.

## Timestampy
Časy jsou ISO-8601 text v UTC, pokud konkrétní doména nevyžaduje explicitní timezone.

## Testování
`tests/python/test_migrations.py` aplikuje všechny migrations do in-memory SQLite s aktivními foreign keys a kontroluje kritické tabulky/indexy/constraints.
