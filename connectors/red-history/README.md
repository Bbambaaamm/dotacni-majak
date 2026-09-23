# ReD historical connector

Historický connector pro oficiální otevřená data Registru dotací Ministerstva financí.

## Oficiální struktura
MF dokumentuje ReD jako propojené tabulky:
- Příjemce pomoci
- Dotace
- Rozhodnutí
- Rozpočtové období

Pro historický kontext Dotačního majáku používáme první tři. Dotace nese projekt/recipient vazbu, Rozhodnutí nese rozhodnutou částku.

Oficiální dokumentace:
- https://data.mf.gov.cz/topics/dotace
- https://data.gov.cz/datov%C3%A1-sada?iri=https%3A%2F%2Fdata.gov.cz%2Fzdroj%2Fdatov%C3%A9-sady%2F00006947%2Feff92c79870f2dba48ac52c3f01635c0

## RAW-first
Všechny tři komprimované CSV soubory se nejprve uloží do RAW snapshot store a až poté parsují.

## Grant-only pravidlo
Rozhodnutí s `navratnostIndikator=true` se nezapočítávají do grant amount. Projekt, jehož všechna rozhodnutí jsou návratná finanční pomoc, se do historical grant examples vůbec nezařadí.

## Aktualizace
ReD katalog uvádí čtvrtletní aktualizaci tabulky Dotace. Refresh má být nízkofrekvenční; connector není realtime source.

## Omezení
- Historický záznam není aktivní výzva.
- Amount je součet známých nenávratných `castkaRozhodnuta`.
- Chybějící rozhodnutí → amount zůstává UNKNOWN.
- Historická podobnost nikdy není success probability.
