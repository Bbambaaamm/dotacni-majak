# Historical Intelligence

Historická podpora je samostatná doména. Nikdy se nesmí zobrazit jako aktuální otevřená výzva.

## Účel
Uživatel může u svého projektu vidět:
**Podobné dříve podpořené projekty**

To poskytuje kontext:
- co se v minulosti financovalo,
- komu,
- v jakém roce,
- z jakého programu,
- v jaké částce, pokud je veřejně dostupná.

## Zakázaná interpretace
Historická data se NESMÍ používat k tvrzení:
- „máte X % šanci dotaci získat“,
- „tento projekt pravděpodobně uspěje“,
- „podobný projekt byl podpořen, tedy váš je způsobilý“.

Historie je kontext, nikoliv eligibility engine ani predikce.

## Datový model
- `historical_awards`
- `historical_award_ontology_terms`

Historické záznamy jsou identifikovány zdrojem + external_id a mají vlastní source_url.

## Similarity
První verze používá deterministický překryv ontology terms. Výsledek vrací sdílené pojmy a similarity signal, nikoliv success probability.

## UI
Každá karta musí být výrazně označena:
**Historický příklad**

A musí obsahovat původní zdroj.
