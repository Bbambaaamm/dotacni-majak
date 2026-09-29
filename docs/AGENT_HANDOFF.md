# Agent Handoff — Dotační maják

Tento dokument je vstupní instrukce pro AI agenta, který pokračuje ve vývoji.

## Mise
Buduj **Dotační maják — Najde. Pohlídá. Dotáhne.** jako důvěryhodnou open-source veřejnou službu pro české uživatele.

## Orchestrace projektu
- Root completion program je GitHub issue **#662** (`HERDR CONTROL · Dotační maják completion program → MVP → Beta → v1.0`).
- **Herdr** je execution/policy control plane; **dotacni-majak-hermes** je stabilní persistent parent/coordinator.
- Hermes před každým slice znovu načte `main`, otevřené PR/issue, readiness/roadmap a durable evidence; nesmí duplikovat již běžící práci.
- Hermes volí nejbližší dependency-safe kritický slice, deleguje bounded child nodes a po merge ihned replanuje další krok.
- Child agenti implementují/researchují/testují/reviewují v izolovaných worktree; permissions child ⊆ parent.
- Merge gate: testy → zelené CI/security/dependency kontroly → independent review PASS na přesném head SHA → ověřit nezměněný head → merge.
- Pozdější milestone nesmí předběhnout otevřený P0 dependency blocker jen proto, že má novější issue číslo.
- Bez lidského zásahu pokračuj autonomně; zastav pouze na credential/billing/production-deploy/irreversible-action nebo skutečně neřešitelném bezpečnostním/produktovém blockeru.
- Root issue #662 zůstává otevřený až do splnění Public Beta a **#41 v1.0 production readiness gate**.

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
