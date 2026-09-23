# Zero-cost-first

Cíl: vývoj a první běžný veřejný provoz bez povinných placených služeb.

Preferovaná architektura:
- Web/PWA: Cloudflare
- API: Workers
- DB: D1
- RAW: R2
- semantic active-call index: Vectorize
- runtime embeddings: Workers AI, pokud aktuálně free/vhodné
- heavy ingestion: Python + GitHub Actions public repo

## Zásady
- limity vždy ověřit v aktuální oficiální dokumentaci před implementací,
- žádný automatický paid upgrade,
- free-tier exhaustion → graceful degradation,
- semantic unavailable → FTS + ontology + structured filters,
- UsageBudgetManager sleduje spotřebu.

## Co měřit
- Workers requests,
- D1 rows read/written/storage,
- R2 storage/operations,
- vector stored/queried dimensions,
- model usage,
- GitHub Actions.

Varování např. 70/85/95 %.

## Finanční bezpečnost produktu
Externí provider nesmí být přidán tak, aby po vyčerpání free limitu začal bez explicitního schválení účtovat.
