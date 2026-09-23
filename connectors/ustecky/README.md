# Ústecký kraj — programové dotace connector

## Autoritativní zdroje
- https://www.kr-ustecky.cz/dotace
- veřejné stránky „Programové dotace Ústeckého kraje“ pro jednotlivé oblasti
- strukturované detailní stránky jednotlivých programů

## Discovery
Connector prochází veřejné server-rendered seznamy programových dotací pro oblasti regionálního rozvoje, školství/sportu, kultury, sociálních věcí, zdravotnictví, životního prostředí, podnikání/transformace a přímé programové odkazy oblasti informatiky/IZS.

Nepoužívá interní endpoint vyhledávání Dotačního kalendáře ani přihlášený Portál dotací a služeb.

## Detail
Oficiální detail může publikovat přímo:
- Kód výzvy
- Oblast dotace
- Finanční alokaci
- Datum zahájení/ukončení sběru žádostí
- Stav programu
- Typ žadatele
- Materiály
- elektronický aplikační odkaz

Peníze se ukládají jako integer minor units.

## Safety
- RAW-first
- GuardedHttpClient
- disappearance != cancellation
- explicitní stav a explicitní data mají přednost před inference
- aplikační portál se nescrapuje
- pouze materiály na oficiálním krajském hostu se stahují jako artifacts
- live smoke je oddělený od fixture CI

## Region
CZ042 — Ústecký kraj.
