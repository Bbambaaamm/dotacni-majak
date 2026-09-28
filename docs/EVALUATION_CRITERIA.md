# Evaluation / Scoring Criteria

## Rozdělení od eligibility

Dotační maják rozlišuje tři nezávislé hodnoticí dimense:

- **Relevance** — „Je výzva tematicky relevantní?“ (search)
- **Eligibility** — „Splňuje tento konkrétní žadatel známé podmínky?“ (eligibility rules)
- **Evaluation / scoring** — „Jaké jsou oficiální hodnoticí kritéria a body, které
  výzva používá k posouzení podnětů?“

Hodnoticí kritéria (evaluation criteria) jsou modulovány **odděleně** od eligibility.
Neslouží jcomo filtr „ano/ne“, ale jako oficiální popis toho, jak je žádost hodnocena
a body přidělovány.

## Model

`grant_evaluation_criteria` je immutable řádek navázaný na konkrétní
`GrantCallVersion`. Každé kritické tvrzení má:

- `evidenceId` → odkaz na `FieldEvidence` (neexistující evidence blokuje, never)
- `verificationStatus` — rozlišuje oficiální extrahovaný fakt od user inputu
- `completenessStatus` — COMPLETE / PARTIAL / UNKNOWN

## Pole

| Pole | Typ | Popis |
|---|---|---|
| `criterionType` | enum | Oficiální kategorie: EXCELLENCE, IMPACT, QUALITY, FEASIBILITY, BUDGET, TEAM, IMPLEMENTATION, SUSTAINABILITY, COMPLIANCE, OTHER |
| `title` | string | Název kritéria dle oficiálního zdroje |
| `description` | string? | Podrobný popis kritéria |
| `pointsMax` | int? | Maximální body (pro skórovací kritéria); null když zdroj neuvádí |
| `weight` | number? | Váha váženého skóre; null když zdroj neuvádí |
| `threshold` | number? | Minimální skóre pro projití (pro vylučovací kritéria); null když není uvedeno |
| `necessity` | enum | REQUIRED / CONDITIONAL / RECOMMENDED — zachování conditional semantics |
| `conditionGroupId` | string? | Volitelný odkaz na `rule_groups`, který řídí podminnost započitání |
| `sortOrder` | int |Determin. pořadí kritéria v rámci výzvy |
| `evidenceId` | string? | Provenance — odkaz na immutable `DocumentVersion` přes `FieldEvidence` |
| `completenessStatus` | enum | COMPLETE / PARTIAL / UNKNOWN |
| `verificationStatus` | enum | AUTO_EXTRACTED / PARTIALLY_VERIFIED / VERIFIED / NEEDS_REVIEW |

## Safety rules

- **Žádné „šance“**: schema neobsahuje žádné pole pro pravděpodobnost úspěchu,
  match score nebo podobný odhad. Body a prahy jsou pouze oficiální fakta.
- **UNKNOWN ≠ FAIL**: chybějící body nebo prahy znamenají UNKNOWN, nikoli automatické selhání.
- **Evidence required**: každé kritécium s `completenessStatus` ≠ UNKNOWN by mělo
  mít `evidenceId`. Absentující evidence s úplnými daty → `NEEDS_REVIEW`.
- **Immutable versioning**: kritéria jsou navázána na `GrantCallVersion`. Změna
  oficiálních kritérií vytvoří novou verzi výzvy.
