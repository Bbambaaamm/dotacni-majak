# Applicant Profile & official resolvers

## Principle
Profil rozlišuje:
- údaje potvrzené uživatelem,
- údaje rozřešené z oficiálních veřejných zdrojů,
- UNKNOWN.

Resolver nikdy pouze podle právní formy ARES automaticky netvrdí, že je subjekt například „sportovní klub“ nebo „neziskovka“. Takové mapování vyžaduje samostatné explicitní pravidlo/ověření.

## ARES
Oficiální veřejné REST API:
- base: `https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/`
- detail: `GET /ekonomicke-subjekty/{ico}`
- Swagger: `https://ares.gov.cz/swagger-ui/`

Resolver ukládá pouze minimální fakta potřebná pro dotační eligibility:
- IČO
- obchodní název
- právní forma
- obec/adresa
- CZ-NACE

Celou odpověď ARES pro uživatelský profil zbytečně nepersistujeme.

ARES 1. 9. 2026 oznámil zpětně nekompatibilní API 1.40 plánované na 30. 9. 2026. Proto parser toleruje více reprezentací základních polí a live contract smoke běží odděleně od PR CI.

## Population / ČSÚ
Autoritativní zdroj pro počet obyvatel:
ČSÚ DataStat, dataset `OBY02E` (počet obyvatel až na úroveň obcí).

DataStat poskytuje veřejné API pro ad-hoc výběry:
`POST /api/dotaz/v1/data/sady/{sadaKod}/vlastni`.

Core applicant package definuje `MunicipalityPopulationResolver`. Konkrétní DataStat import/cache bude implementován samostatně; profil uchovává vždy:
- population
- as_of date
- source_reference

Tím se starší populační údaj nikdy netváří jako aktuální bez data platnosti.
