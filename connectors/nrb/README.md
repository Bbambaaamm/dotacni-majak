# NRB connector

Oficiální Source Adapter pro veřejné produkty Národní rozvojové banky.

## Discovery
- úvěry: https://www.nrb.cz/podnikatele/uvery/
- záruky: https://www.nrb.cz/podnikatele/zaruky/

Publikují se pouze produktové detail pages `/produkt/...`.

## Typ finančního nástroje
- produkt ze sekce Záruky → `GUARANTEE`
- produkt ze sekce Úvěry → `LOAN`
- úvěr s explicitní dotační/příspěvkovou složkou → `MIXED`

Current grantový finance engine tyto negrantové nástroje nepočítá. Vrací `INSTRUMENT_NOT_SUPPORTED`, dokud nevznikne specializovaný kalkulátor.

## Status
- Aktivní příjem žádostí → OPEN
- explicitně pozastavený příjem → PAUSED
- budoucí plánované spuštění → PLANNED
- ukončený příjem → CLOSED
- jinak UNKNOWN

## Extrakce
Kde jsou údaje na stránce:
- výše úvěru,
- procento záruky,
- úrok,
- splatnost,
- příspěvková/dotační složka,
- cíloví žadatelé,
- geografické omezení,
- oficiální PDF/DOC/XLS dokumenty.

## Safety
- RAW-first,
- žádný scraping WebKlienta/e-podatelny,
- záruka se nikdy neprezentuje jako dotace,
- PAUSED se nemaskuje jako CLOSED,
- UNKNOWN zůstává UNKNOWN.
