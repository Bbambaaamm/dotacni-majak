# EU Funding & Tenders connector

Oficiální zdroj: European Commission Funding & Tenders Portal.

## API
Dokumentace:
https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis

SEARCH:
`https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***`

## Discovery query v0.1
- programmePeriod: 2021 - 2027
- status: Forthcoming + Open
- type: 1 + 8

Type mapping je explicitně omezený na grant/cascade grant kandidáty používané v této verzi. Rozšíření type scope musí projít fixture/live contract review, aby se do grant výsledků nepřimíchaly procurement records.

## Ověřený live contract — 2026-09-23
Top-level API response obsahuje mimo jiné:
- pageNumber
- pageSize
- totalResults
- results

Result obsahuje:
- reference
- url
- summary
- metadata

Metadata používá převážně jednoprvková pole a obsahuje např.:
- identifier
- title
- status
- startDate
- deadlineDate
- frameworkProgramme
- callTitle
- type
- budgetOverview
- topicConditions
- latestInfos
- links

`budgetOverview` je JSON string a adapter ho parsuje do `budgetOverviewParsed`.

`topicConditions` obsahuje HTML; adapter z něj pouze bezpečně vytahuje veřejné dokumentové URL na `ec.europa.eu`. HTML se nikdy nespouští.

## Upstream anomálie
Open status není sám o sobě dostatečný. Adapter filtruje OPEN topic, jehož deadline je již v minulosti.

## RAW-first
Discovery response může být uložen jako RAW snapshot a každý detail NativeRecord vždy vyžaduje RAW snapshot.

## Live smoke
Samostatný workflow ověřuje:
healthcheck → discovery → topic detail → RAW snapshot.

Běžné CI používá fixture a není závislé na dostupnosti externího API.
