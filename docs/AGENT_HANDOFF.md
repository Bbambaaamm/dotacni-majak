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
- Bez lidského zásahu pokračuj autonomně; zastav na credential/billing/production-deploy/irreversible-action, skutečně neřešitelném bezpečnostním/produktovém blockeru **a na každém explicitním human release gate**.
- Public Beta ani v1.0 nesmí Hermes sám prohlásit za schválené: pokud gate vyžaduje reálné uživatelské/usability evidence, manuální audit, lidského reviewera nebo explicitní GO/NO-GO rozhodnutí, připrav všechny automatizovatelné podklady a pak eskaluj člověku bez fabrikace důkazů.
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

## Validace odpovědi vyhledávání
Klient výsledků kontroluje úspěšnou odpověď Search API před vykreslením: záměr musí odpovídat požadavku, seznam výsledků, stránkovací kurzor a facets musí mít smluvený tvar. Neplatná či neúplná odpověď se zobrazí jako chyba s možností opakování; nesmí být vydávána za prázdný katalog nebo za konec stránkování.

## Validace detailu výzvy
Klient detailu ověřuje úspěšnou odpověď API před vykreslením: identita výzvy musí odpovídat požadavku, základní verze, poskytovatel, dostupnost, zdroje, podmínky, scénáře a doklady musí mít smluvený tvar. Chybějící či poškozený údaj se nesmí vykreslit jako ověřená podmínka nebo nulový počet dokladů; zobrazí se chyba s možností opakování. HTTP 404 zůstává odlišné od poškozené úspěšné odpovědi.

## Návrat z detailu do vyhledávání
Detail přenáší v URL pouze ověřené parametry záměru, aktivních API filtrů a řazení. Zpětný odkaz obnoví filtry a první stránku výsledků novým požadavkem na API. Stránkovací kurzor ani dříve načtené stránky se neukládají a po návratu se neobnovují.

## Doklady v detailu výzvy
Detail API vrací nejvýše 100 dokladů. Pokud termín, scénář financování nebo požadavek odkazuje na `evidenceId`, který v omezeném seznamu chybí, UI uvede, že doklad není v tomto seznamu dostupný, a vyzve k ověření v oficiálním zdroji. Pouze `evidenceId: null` znamená, že samostatný doklad není připojen. Chybějícímu dokladu UI nepřiřazuje název, odkaz ani stav ověření.

## Omezené seznamy v detailu výzvy
Detail API vrací nejvýše 20 zdrojových záznamů, 20 změn a 20 verzí. Při dosažení limitu UI upozorní, že seznam nemusí být úplný. Zobrazených 20 chybějících zdrojových záznamů nevylučuje další záznam se stavem `SEEN`; chybění samo o sobě neznamená zrušení výzvy. E2E fixture `grant:e2e:history` obsahuje 21 zdrojových záznamů (poslední v řazení je `SEEN`) a 21 změn mezi verzemi 21 a 22 pro ověření těchto hranic v reálném D1/API/Chromium běhu.

## Definition of Done
Kód je otestovaný, CI zelené, docs aktualizované, failure mode bezpečný a UX nevytváří falešnou jistotu.
