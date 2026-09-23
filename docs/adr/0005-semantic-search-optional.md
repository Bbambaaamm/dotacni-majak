# ADR-0005: Semantic search je volitelná nadstavba

## Status
Accepted

## Decision
Semantic retrieval není source of truth ani single point of failure. Core search musí fungovat přes FTS5 + dotační ontologii + strukturované filtry i bez embedding provideru nebo vector indexu.

Aktivní/plánovaná výzva má kompaktní `SearchProfile`, typicky jeden hlavní vektor na `GrantCallVersion`, místo masivního vektorování všech odstavců všech PDF.

Embedding provider a vector index jsou rozhraní. Cloudflare Workers AI / Vectorize mohou být produkční adapter, ale core package na nich není závislý.

## Budget
Vector budget je explicitní runtime konfigurace. Žádné free-tier limity nejsou hardcoded jako architektonická pravda.

K 23. 9. 2026:
- Cloudflare dokumentuje `@cf/baai/bge-m3` jako multilingual 1024D embedding model.
- Vectorize pricing dokumentace uvádí free kvóty pro stored/queried dimensions.
- jiná Workers pricing stránka současně obsahuje formulaci, že Vectorize je dostupný pouze na Paid plánu.

Kvůli této nekonzistenci se dostupnost/free režim ověřuje znovu při deploymentu a nikdy není předpokladem funkce Majáku.

## Consequences
- semantic failure → explicitní unavailable result, ne chyba celého search requestu,
- budget exhaustion → fallback,
- full-document provenance/search zůstává mimo vector index,
- model/provider lze měnit bez změny search domény.
