# DotaceEU.cz connector

Oficiální zdroj: Ministerstvo pro místní rozvoj / DotaceEU.cz.

- Listing: https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy
- Detail: veřejné stránky jednotlivých výzev
- Discovery: preferovaně veřejný XLSX „Stáhnout kalendář“ nalezený přímo v HTML; fallback server-rendered HTML links
- Autorita: OFFICIAL
- Refresh MVP: 4 h
- RAW-first: listing, XLSX i detail se snapshotují

## Proč bez nezdokumentovaného AJAX API

Listing obsahuje „Načíst další“, ale adapter nereverse-engineeruje skrytý endpoint. Místo toho používá veřejně publikovaný XLSX odkaz, pokud workbook obsahuje hyperlinky na detail výzev. Pokud workbook/hyperlinky nejsou dostupné, použije omezený server-rendered HTML fallback a Source Health/live smoke musí odhalit regresi coverage.

## Detailní metadata

DotaceEU detail veřejně obsahuje mimo jiné:
- číslo výzvy,
- druh výzvy,
- programové období,
- operační program,
- prioritní osu,
- oprávněné žadatele,
- zpřístupnění žádosti,
- otevření/uzavření příjmu,
- stav,
- odkaz na další oficiální informace,
- historii aktualit/změn.

## Scope boundary

DotaceEU je oficiální agregátor a významný discovery/provenance zdroj. Programové dokumenty se mají získávat přes příslušné provider connectors (OPŽP, IROP, OP TAK atd.), nikoli domýšlet z DotaceEU.
