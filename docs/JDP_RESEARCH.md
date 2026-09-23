# JDP / RISPF public retrieval research

Issue: #15

## Stav: ověřeno 2026-09-23

Public unauthenticated portal:

- https://jdp2.mf.gov.cz/

reálně používá read-only public dashboard API bez přihlášení.

## Ověřené endpointy použité connector-em

- GET `/jdp_api/api/NxWebEDPPublicDashboard/KodyVyzvaStav`
- POST `/jdp_api/api/nxwebedppublicdashboard/kodyvyzva`

Pozorovaný OPEN request používá JSON body:

- `stavVyzvaLong = Běžící`
- `stavVyzvaLongWeb = Otevřená`
- zero-based `pageIndex`
- `pageSize`
- sort podle `datumKonec`

Response obsahuje stránkování a u položek mimo jiné:

- `id`, `kod`, `nazev`, `popis`
- `datumZacatek`, `datumKonec`
- `stavVyzva*`
- `castkaPodporaZadostMin/Max`
- `castkaVyzvaCelkem`
- `miraPodporaZadostMax`
- `typLong`, `link`

## Safety boundary

Connector používá pouze veřejný dashboard. Nepoužívá:

- login,
- uživatelský profil,
- neveřejné žadatelské endpointy,
- CAPTCHA bypass,
- cookies/auth jako source contract.

V0.1 záměrně ingestuje pouze **otevřené** výzvy, protože pro tento stav máme přesně ověřený request template. Plánované/pozastavené stavy se rozšíří pouze po samostatném contract capture; žádný filter se neodhaduje.

## RAW-first

Celá response page se uloží jako immutable RAW snapshot. NativeRecord odkazuje na tento snapshot a zachovává původní veřejné hodnoty; finanční source values nejsou bez důkazu reinterpretovány.

## Datumy

Timezone-less JDP timestamp je interpretován jako `Europe/Prague` a až poté převáděn do UTC. Původní textový timestamp zůstává v `raw_fields`.
