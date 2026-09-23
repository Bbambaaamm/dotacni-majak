# JDP connector

Oficiální zdroj: https://jdp2.mf.gov.cz/

## Retrieval

Veřejná homepage JDP sama bez přihlášení používá public dashboard API:

- GET `/jdp_api/api/NxWebEDPPublicDashboard/KodyVyzvaStav`
- POST `/jdp_api/api/nxwebedppublicdashboard/kodyvyzva`

První connector záměrně ingestuje pouze veřejně otevřené výzvy přes přesně
pozorovaný request template:

- `stavVyzvaLong = Běžící`
- `stavVyzvaLongWeb = Otevřená`
- řazení podle `datumKonec`.

Další stavy se nepřidávají odhadem. Budou rozšířeny až po zachycení jejich
veřejných request templates.

## Data z list payloadu

API veřejně poskytuje mimo jiné:
- ID/kód/název/popisek,
- stav,
- začátek/konec podání,
- min/max částku podpory,
- celkovou alokaci,
- maximální míru podpory jako source value,
- typ nástroje,
- public link.

RAW response se ukládá jako immutable snapshot a record používá jeho snapshot ID.

## Finance safety

Částky se normalizují do integer minor units.
`miraPodporaZadostMax` se zatím zachovává jako source value; její jednotka/scale
se neinterpretuje v connectoru bez samostatné finance normalization evidence.


## TLS / live smoke — 2026-09-23

GitHub-hosted Python runner při live smoke odmítá TLS řetězec `jdp2.mf.gov.cz` chybou `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`.

Dotační maják **nevypíná ověřování certifikátu** a nepřidává neověřený bypass. Fixture/contract testy jsou zelené; live source health proto zůstává v daném prostředí `UNAVAILABLE`, dokud poskytovatel neopraví řetězec nebo nevznikne samostatně reviewované bezpečné řešení důvěry.
