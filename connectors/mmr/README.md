# MMR connector

Oficiální veřejný Source Adapter pro národní dotační programy Ministerstva pro místní rozvoj.

## Discovery
Seed: https://mmr.gov.cz/cs/narodni-dotace

Adapter provádí omezený crawl pouze v podstromu `/cs/narodni-dotace`:
1. centrální index,
2. tematické/programové indexy,
3. konkrétní call stránky.

Maximální počet indexových stránek je omezený a pouze aktuální/následující rok se publikuje jako kandidát.

## Scope
- veřejné HTML call pages,
- PDF/DOCX/XLS/XLSX přílohy,
- termín otevření/uzavření,
- aktualizace deadline z textu,
- call code,
- účel/oprávnění žadatelé,
- application method.

## Mimo scope
Autentizovaný DIS ZAD. Connector se do něj nepřihlašuje ani neobchází autentizaci.

Coverage je transparentně označeno jako neúplné, dokud nemáme contract coverage všech tematických větví.
