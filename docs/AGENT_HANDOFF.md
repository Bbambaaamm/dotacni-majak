# Agent Handoff — Dotační maják

Tento dokument je vstupní instrukce pro AI agenta, který pokračuje ve vývoji.

## Mise
Buduj **Dotační maják — Najde. Pohlídá. Dotáhne.** jako důvěryhodnou open-source veřejnou službu pro české uživatele.

## Před prací vždy přečti
1. README.md
2. ARCHITECTURE.md
3. DATA_MODEL.md
4. SOURCE_ADAPTERS.md
5. INGESTION.md
6. ROADMAP.md
7. docs/ISSUE_ROADMAP.md
8. docs/PRODUCT_SPEC.md
9. docs/UX_PRINCIPLES.md
10. DESIGN_SYSTEM.md
11. relevantní ADR

## Priorita při konfliktu
1. přesnost dotačních údajů
2. provenance
3. bezpečnost
4. ochrana proti falešným závěrům
5. vysvětlitelnost
6. end-to-end vyřešení uživatelova problému
7. jednoduchost/accessibility
8. spolehlivost
9. zero-cost
10. výkon
11. počet funkcí

## Nezpochybnitelné invariants
- official source = source of truth,
- UNKNOWN != FAIL,
- relevance != eligibility,
- AI není jediný rozhodovací mechanismus,
- finance/rules jsou deterministické,
- immutable versioning,
- RAW-first,
- provenance u kritických tvrzení,
- disappearance != cancellation,
- parser failure nesmí provést destructive changes,
- žádný auto-pay,
- každý klíčový screen má „Co mám udělat teď?“.

## Vývojový workflow
- pracuj přes issue → branch → PR,
- malé reviewovatelné PR,
- tests + CI,
- connector používá fixtures,
- live smoke test odděleně,
- canonical schema měň jen přes ADR/review,
- po merge navazuj z čerstvého main; nepokračuj stacked historií přes squash bez vyčištění.

## Definition of Done
Kód je otestovaný, CI zelené, docs aktualizované, failure mode bezpečný a UX nevytváří falešnou jistotu.
