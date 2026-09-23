# Národní sportovní agentura connector

Oficiální zdroje:
- https://nsa.gov.cz/dotace-investicni/
- https://nsa.gov.cz/dotace-neinvesticni/
- https://nsa.gov.cz/dotace-neinvesticni-parasport/

## Retrieval
Veřejné HTML listingy → detail výzvy → veřejné dokumenty v `wp-content/uploads`.

## Live contract 2026-09-23
Detail výzvy používá:
- H1 = název,
- H2 label/value pro datum vyhlášení, zahájení, ukončení a alokaci,
- text „Příjem žádostí byl ukončen.“ jako explicitní CLOSED signal,
- veřejné odkazy na aktuální znění výzvy, dodatky, návody, FAQ a přílohy.

Stav se neurčuje pouze podle listingu. Priorita:
1. explicitní CLOSED text,
2. end datetime v minulosti,
3. start datetime v budoucnosti = PLANNED,
4. známé časové okno = OPEN,
5. jinak UNKNOWN.

## Golden fixture
Výzva 16/2026 Regiony 2026 – investice pod 10 mil. Kč obsahuje popis:
„výstavbu a technické zhodnocení sportovních zařízení místního významu…“

To je referenční zdroj pro budoucí search regression „rekonstrukce tenisových kurtů“.

## RAW-first
Listing i detail jsou snapshottované před normalizací. Dokumenty jsou samostatné RAW snapshots.

## Connectivity
GitHub-hosted runner při jednom pokusu zaznamenal connect timeout, následná IPv4 diagnostika i live probe uspěly. Source Health proto musí běžný dočasný transport failure interpretovat jako UNAVAILABLE, nikoliv jako zrušení výzev.
