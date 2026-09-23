# Plzeňský kraj — eDotace connector

## Autoritativní zdroj
https://dotace.plzensky-kraj.cz/verejnost

Portál veřejně publikuje otevřené a připravované krajské dotační tituly a na detailu uvádí podmínky, žadatele, termíny, finance, administrátory a přílohy.

## Discovery
Server-rendered HTML index. Detailní URL má stabilní tvar:
`/verejnost/dotacnititul/{numeric_id}/`

Source external identity:
`PLK-{numeric_id}`

## Normalizovaná metadata
Connector získává:
- title
- publication/application dates
- status podle explicitních application dates
- purpose/reason text
- eligible applicants text
- total allocation
- maximum requested grant
- region CZ032
- attachments

Peníze jsou v RAW fields uloženy jako integer minor units.

## Safety
- RAW-first
- GuardedHttpClient
- disappearance from index != CLOSED/CANCELLED
- application status se odvozuje pouze z explicitních termínů
- attachment download zůstává na allowlisted official hostu
- fixtures + separate live smoke

## Coverage
Index veřejně rozlišuje otevřené a připravované tituly. Historicky ukončené tituly nejsou primárním cílem monitoringu nových příležitostí.
