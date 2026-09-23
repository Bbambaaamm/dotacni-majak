# MPSV national grants connector

Oficiální Source Adapter pro vybrané národní dotační oblasti Ministerstva práce a sociálních věcí.

## Aktuální coverage v0.1
- dotační titul **Rodina** přes stabilní programový index,
- národní financování **sociálních služeb** přes roční index `Finanční prostředky pro rok YYYY`.

Connector záměrně **netvrdí úplné pokrytí všech dotačních titulů MPSV**. Další programové indexy se přidávají explicitně po ověření oficiální retrieval cesty.

## Zdroj
- https://mpsv.gov.cz/dotace-na-podporu-rodiny-pro-nestatni-neziskove-organizace-v-dotacnim-rizeni-rodina
- https://mpsv.gov.cz/financni-prostredky-pro-rok-2026

## Extrakce
- program / rok,
- účel / věcné zaměření,
- oprávnění žadatelé,
- způsob podání,
- termín otevření/uzavření,
- maximální požadovaná částka, pokud je jednoznačně uvedená,
- povinné přílohy jako text,
- oficiální dokumenty jako RAW-first artifacts.

## Safety
- disappearance != cancellation,
- žádné přihlášené aplikace OKslužby se nescrapují,
- zdrojové stránky a dokumenty mají RAW snapshot,
- coverage caveat je součástí raw fields.
