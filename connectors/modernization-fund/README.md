# Modernizační fond / SFŽP connector

Oficiální zdroj: Státní fond životního prostředí ČR.

- Listing: https://sfzp.gov.cz/dotace-a-pujcky/modernizacni-fond/vyzvy/
- Detail: `detail-vyzvy/?id=<id>`
- Retrieval: veřejné HTML + veřejné dokumenty
- Autorita: OFFICIAL
- Refresh MVP: 4 h
- RAW-first: listing, detail i dokumenty

## Extracted data
- title / stable SFŽP detail id
- publication date
- submission open/close
- canonical-safe status fallback from dates
- supported activities text
- eligible applicants text
- maximum support rate when explicitly stated
- allocation
- application instructions
- public documents

## Coverage caveat
Server-rendered listing includes an initial result set and a „načíst další“ control. Adapter intentionally does not reverse-engineer an undocumented AJAX endpoint. Live smoke and Source Coverage must therefore expose any incomplete listing coverage instead of claiming all Modernisation Fund calls are monitored.

## Status safety
Disappearance from listing never means CLOSED/CANCELLED. Cancellation/pausing is mapped only from explicit authoritative text; otherwise date fallback yields PLANNED/OPEN/CLOSED.
