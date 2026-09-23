# DZS connector

Oficiální Source Adapter pro decentralizované grantové termíny publikované Domem zahraniční spolupráce.

## První coverage
- Erasmus+ — veřejná stránka Výzvy 2026
- Evropský sbor solidarity — Projekty a granty / termíny 2026

Connector rozděluje jeden oficiální přehled na samostatné grantové příležitosti podle akce a termínu.

## Efektivita
Discovery stáhne každou zdrojovou stránku jen jednou. `fetch_record` používá data a RAW snapshot z discovery a stránku znovu nestahuje pro každou jednotlivou akci.

## Status
Budoucí/aktuální deadline je mapován konzervativně na OPEN, uplynulý na CLOSED. Pokud datum nelze určit, status je UNKNOWN.

## Scope limit
Centralizované aktivity Erasmus+ spravované přímo Evropskou komisí nejsou duplikovány; patří do EU Funding & Tenders connectoru.

## Safety
- RAW-first
- žádné scraping přihlášených aplikačních systémů
- official DZS only
- UNKNOWN není FAIL
