# Governance

Dotační maják je maintainer-led open-source projekt.

## Rozhodování

### Běžné změny
Issue → branch → PR → CI → review → merge.

### Architektonické změny
Vyžadují ADR, pokud mění:
- canonical schema nebo versioning,
- Source Adapter Contract,
- eligibility DSL,
- provenance model,
- bezpečnostní invariants,
- zero-cost zásady,
- privacy model.

### Data source změny
Každý connector musí:
- používat oficiální nebo explicitně označený sekundární zdroj,
- respektovat technické ochrany a podmínky zdroje,
- mít fixtures,
- oddělit live smoke od běžného CI,
- nikdy neinterpretovat disappearance jako cancellation bez důkazu.

## Merge pravidla

PR je připraven k merge, když:
- relevantní CI je zelené,
- diff je reviewovatelný a scoped,
- testy pokrývají kritické failure states,
- dokumentace odpovídá implementaci,
- nevzniká skrytá placená závislost,
- nedochází k oslabení provenance/security invariantů.

## Releases

Veřejná Beta a v1.0 mají vlastní release gates v roadmapě.

v1.0 vyžaduje minimálně:
- security review,
- privacy review,
- accessibility audit,
- source coverage audit,
- regression/search-quality suite,
- recovery/runbook kontrolu.

## Přístup k veřejné značce

Fork může používat zdrojový kód podle MIT licence. Nesmí však bez jasného
odlišení působit jako oficiální instance původního projektu Dotační maják.
