# Karlovarský kraj connector

## Autoritativní zdroj
https://www.kr-karlovarsky.cz/dotace/dotacni-programy-karlovarskeho-kraje

Veřejný katalog publikuje dotační programy Karlovarského kraje, filtr podle oblasti/stavu a detailní stránky s explicitním stavem a termíny.

## Discovery
Server-rendered katalog + veřejné pagination odkazy `?page=N`.

Program detail má stabilní slug pod `/dotace/{slug}`. External identity je deterministicky odvozena z path + hash.

## Metadata
- provider status (PLANNED / OPEN / CLOSED / PAUSED)
- electronic submission dates
- area
- contact
- official documents
- region CZ041

## Safety
- RAW-first
- GuardedHttpClient
- login/application portal se nescrapuje
- disappearance != cancellation
- stav se mapuje z explicitního textu poskytovatele
- detailní termíny se preferují před date-only summary
- fixtures + live smoke
