# Jihočeský kraj — vyhlášené dotace connector

## Autoritativní zdroj
https://www.kraj-jihocesky.cz/ku_dotace/vyhlasene

Oficiální stránka Jihočeského kraje publikuje aktuálně vyhlášené dotační programy včetně charakteristiky, harmonogramu a souborů.

## Discovery
Connector používá pouze server-rendered veřejné HTML. Každý grant je na stránce oddělen nadpisem:
`Datum zveřejnění: <datum> <název>`.

Zdrojová identita je deterministická kombinace data zveřejnění a normalizovaného názvu, protože stránka neposkytuje samostatné veřejné ID pro každou položku.

## Normalizovaná metadata
- title
- publication date
- submission open/close
- status podle explicitního harmonogramu
- characteristic / supportedActivitiesText
- application URL, pokud je veřejně uvedeno
- official artifacts
- region CZ031

## Safety
- RAW-first
- GuardedHttpClient
- disappearance != CLOSED/CANCELLED
- datum sejmutí z úřední desky se nepoužívá jako application deadline
- application window pochází pouze z explicitního Harmonogramu
- externí aplikační portál se nescrapuje
- fixture tests + live smoke

## Coverage caveat
Jedna výzva může mít více cílových skupin s různými termíny (např. školy vs. rodiče). Obecný Harmonogram se uloží jako primární source window a celý section text se zachová v `applicationWindowNotes` pro pozdější přesnější applicant-specific extraction.
