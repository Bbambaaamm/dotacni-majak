# Liberecký kraj — Dotace connector

## Autoritativní zdroj
https://dotace.kraj-lbc.cz/

Veřejný krajský portál obsahuje rozcestník oblastí podpory, seznamy jednotlivých dotačních programů a detailní programové stránky.

## Discovery
1. veřejný root portálu,
2. veřejné kategorie/oblasti,
3. detail programu s URL obsahující stabilní veřejné číselné ID (`-d<ID>.htm`).

Záštity bez finanční podpory jsou z discovery explicitně vyřazeny.

## Detail
Connector získává:
- title
- published/announcement date
- submission open/close
- status z explicitního časového okna
- summary / aktuální popis
- total allocation, pokud je explicitně publikována
- official downloadable artifacts
- region CZ051

## Safety
- RAW-first
- GuardedHttpClient
- disappearance != cancellation
- žádný login ani automatizace dotačního portálu s Identitou občana
- status není přebírán z historického výsledku řízení; vyhodnocuje se z explicitních termínů
- finance pouze z explicitního textu
- live smoke je oddělený od fixture CI
