# TA ČR connector

Oficiální Source Adapter pro veřejně vypsané aktuální možnosti podpory Technologické agentury ČR.

## Discovery
Primární zdroj:
- https://tacr.gov.cz/

Connector používá sekci **Aktuální možnosti podpory** a publikuje pouze odkazy na konkrétní stránky `/soutez/`, u kterých TA ČR uvádí, že běží lhůta pro podávání návrhů projektů.

Plánované soutěže z harmonogramu nejsou v první verzi vydávány za OPEN. Jejich přidání vyžaduje samostatné mapování stavu PLANNED.

## Extrakce
Detail soutěže poskytuje strukturované:
- termín vyhlášení výsledků,
- alokaci,
- maximální podporu na projekt,
- maximální intenzitu podpory,
- uchazeče,
- lhůtu pro podání.

Pokud text detailu uvádí přesnější časy soutěžní lhůty, connector je preferuje před souhrnným datem.

## Dokumenty
Oficiální dokumenty TA ČR na povolených hostech se ukládají RAW-first. Zadávací dokumentace je klasifikována jako CALL_DOCUMENT.

## Safety
- GuardedHttpClient,
- RAW-first,
- fixtures + live smoke,
- homepage disappearance není automaticky CANCELLED,
- SISTA se nescrapuje.
