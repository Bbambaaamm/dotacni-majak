# ADR-0004: Zero-cost-first infrastructure

## Status
Accepted

## Decision
První veřejná verze preferuje free tiers a open-source komponenty. Vyčerpání kvóty musí degradovat funkcionalitu, ne automaticky aktivovat placenou službu.

## Consequences
- používání služeb se měří přes UsageBudgetManager,
- semantic retrieval má fallback na FTS + ontologii + filtry,
- placený upgrade vyžaduje explicitní rozhodnutí.
