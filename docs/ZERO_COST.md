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


## Semantic/vector provider caveat (2026-09-23)

Cloudflare dokumentace aktuálně není zcela konzistentní ohledně dostupnosti Vectorize na Workers Free: Vectorize pricing stránka publikuje free kvóty, zatímco Workers pricing stránka současně obsahuje formulaci „currently only available on the Workers paid plan“.

Proto:
- Vectorize není hard dependency,
- limity jsou runtime konfigurace,
- před produkčním deploymentem se plán/dostupnost znovu ověří,
- fallback je vždy FTS5 + ontologie + strukturované filtry,
- systém nikdy neprovede automatický paid upgrade.


## UsageBudgetManager

Limity providera nejsou hardcoded v kódu. Runtime konfigurace dodává pro každý sledovaný metric explicitní `hard_limit`.

Manager standardně používá prahy:
- 70 % → NOTICE / WARN,
- 85 % → WARNING / THROTTLE,
- 95 % → CRITICAL / DEGRADE,
- >100 % → EXHAUSTED / BLOCK nebo explicitně nakonfigurovaný fallback.

Sledované metriky zahrnují:
- Workers requests,
- D1 reads/writes/storage,
- R2 storage/Class A/Class B,
- vector stored/query dimensions,
- AI units,
- GitHub Actions minutes.

Rezervace, která by překročila hard limit, se **nezapočítá**. Volající dostane `granted=false` a musí použít bezpečný fallback. Pro semantic retrieval může být exhausted action explicitně `DEGRADE`, tedy pokračovat přes FTS5 + ontologii + filtry.

Žádný limit v tomto modulu nepředstavuje aktuální ceník poskytovatele; konkrétní čísla se nastavují až po aktuálním ověření oficiální dokumentace.
