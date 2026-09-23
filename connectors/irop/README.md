# IROP 2021–2027 connector

Oficiální zdroj: Ministerstvo pro místní rozvoj / IROP.

- Listing: https://irop.gov.cz/cs/vyzvy-2021-2027
- Discovery: veřejný XLSX kalendář, pokud obsahuje detailní odkazy; HTML fallback
- Detail: veřejná stránka jednotlivé výzvy
- Autorita: OFFICIAL
- Refresh MVP: 4 h
- RAW-first: listing, XLSX, detail a dokumenty

## Detailní metadata

Adapter získává stav, druh výzvy, termíny, oprávněné žadatele, obecné informace, finanční alokaci/statistiky, aktuality/revize a připojené soubory.

## Coverage

HTML listing obsahuje „Načíst další“. Adapter proto nepředpokládá žádný nezdokumentovaný endpoint. Veřejný XLSX kalendář je preferovaný discovery zdroj, pokud obsahuje odkazy na detail. Source Health/live smoke musí signalizovat regresi pokrytí.
