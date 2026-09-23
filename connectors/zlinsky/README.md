# Zlínský kraj — dotační programy connector

## Oficiální zdroj
- https://zlinskykraj.cz/dotace
- veřejné detailní stránky jednotlivých programů
- dokumenty ke stažení na oficiálním hostu

## Detail
Zdroj veřejně publikuje zejména:
- kód programu v názvu,
- termín vyhlášení,
- interval příjmu žádostí,
- finanční alokaci,
- oblast dotace,
- dokumenty,
- u části programů odkazy na elektronické žádosti.

Connector zachovává alokaci také v raw textu a bezpečně převádí jednoduché částky (např. 70 mil. Kč) na integer minor units.

## Safety
RAW-first, GuardedHttpClient, disappearance != cancellation. Online formulář žádosti se nescrapuje.
Region: CZ072.
