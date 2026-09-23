# Moravskoslezský kraj — dotační programy connector

## Autoritativní zdroj
- https://www.msk.cz/cs/temata/dotace/
- veřejné detailní stránky jednotlivých dotačních programů na `msk.cz`
- oficiální podmínky a přílohy publikované na stejném hostu

## Discovery
Connector prochází veřejný topic index „Dotace“ a veřejné pagination odkazy. Za dotační detail považuje pouze oficiální URL ve tvaru:

`/cs/temata/dotace/<slug>-<numeric-id>/`

Nepřistupuje do ePodatelny ani jiných přihlašovaných systémů.

## Detail
Z veřejné stránky zachovává:
- titul,
- kód programu, pokud je explicitně publikovaný,
- původní text termínu,
- jeden bezpečně rozpoznaný interval podání,
- aplikační odkaz,
- oficiální podmínky/přílohy,
- region CZ080.

Pokud text obsahuje více kol/intervalů, connector je nespojuje do falešného kontinuálního období; zachová raw deadline text a stav zůstává UNKNOWN pro navazující parser.

## Safety
RAW-first, GuardedHttpClient, disappearance != cancellation, žádný scraping přihlášené ePodatelny.
