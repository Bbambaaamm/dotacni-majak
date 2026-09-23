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
