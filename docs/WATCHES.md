# Project Watch

Project Watch je hlavní „Pohlídá“ funkce Dotačního majáku.

## Vstupy
Watch matcher nedělá nový AI úsudek. Skládá už existující výsledky:
- relevance (HybridRanker),
- eligibility (deterministic EligibilityEvaluator),
- finance (deterministic FinanceEngine).

## Stavy
- MATCHED
- NEEDS_INFORMATION
- NEEDS_REVIEW
- NOT_ELIGIBLE
- NOT_FINANCIALLY_COMPATIBLE
- NOT_RELEVANT

## Notification candidate
Pozitivní notification candidate:
- MATCHED,
- NEEDS_INFORMATION.

NEEDS_INFORMATION je užitečné upozornění typu:
> Objevila se nová tematicky vhodná možnost. Potřebujeme doplnit vlastnictví areálu.

Neodesílat jako pozitivní „nová možnost“:
- verified INELIGIBLE,
- finance SCENARIO_NOT_APPLICABLE,
- WEAK relevance.

## Deduplikace
Dedupe key zahrnuje:
watch + grant call + GrantCallVersion + resulting status.

Stejná reevaluace stejné verze je UNCHANGED. Nová GrantCallVersion je UPDATED a může vytvořit nový notification event.

## Soukromí
Watch match ukládá projekt/watch IDs a výsledkové stavy/reason codes. Nemá kopírovat celý natural-language záměr do notification/outbox payloadu.
