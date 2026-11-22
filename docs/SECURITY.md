# Security & Threat Model

## Scope
Dotační maják zpracovává nedůvěryhodný obsah z internetu a později uživatelské projektové údaje. Každý externí dokument, HTML, URL i uživatelský vstup je nedůvěryhodný.

## Hlavní aktiva
- integrita canonical dotačních dat a provenance
- uživatelské projekty/profily
- deployment/provider secrets
- notification channels
- dostupnost a reputace služby

## Trust boundaries
1. Oficiální web/API → GuardedHttpClient → RAW store.
2. RAW dokument → parser/extractor → validation/quarantine.
3. Canonical DB → API → web UI.
4. Uživatel → API → project/profile/watch.
5. Outbox → notification/search/vector providers.
6. GitHub CI/CD → deployment.

## Threats a mitigace

### SSRF / redirects
Exact host allowlist, HTTPS, DNS public-address validation, redirect revalidation, bounded POST pouze explicitně, produkčně network egress policy.

### Malicious documents
MIME/size validation, archive/decompression limits, XXE zákaz, embedded URL bez auto-fetch, OCR izolovaný fallback, parser failure → quarantine.

### Injection / XSS
Žádný arbitrary eval rules, SQL parametrizace, externí HTML nikdy jako trusted HTML, React escaping, CSP před beta.

### CSRF / auth
Při serverové autentizaci SameSite/token model, CSRF protection pro cookie mutations, session rotation/revocation a rate limits.

### IDOR / authorization
Každý project/workspace/watch/share objekt má server-side owner/permission check. Klientský route guard není authorization.

### Share links
Vysoká entropie, revocable, read-only default, noindex, konfigurovatelná expirace a žádný citlivý payload přímo v URL.

### Notification abuse
Opt-in, rate limits, dedupe, unsubscribe/revoke a ověření destination.

### Supply chain / secrets
Lockfiles, dependency scanning, minimální Actions permissions, secrets mimo repo/fixtures, log redaction.

### Data poisoning
Source authority registry, RAW SHA-256, quality gate, provenance, last-known-good a blokace destructive changes při DEGRADED source.

### Resource abuse
Request/body/file limits, concurrency/rate budgets, bounded search fan-out, UsageBudgetManager a caching.

`GET`/`HEAD /search` přijímá nejvýše 16 384 znaků v zakódovaném query stringu (bez `?`); delší dotaz vrací HTTP 400 `QUERY_TOO_LONG` před čtením D1. Každý známý parametr vyhledávání může být uveden nejvýše jednou, včetně `intent`, `limit` a `cursor`; opakování vrací HTTP 400 i při totožných hodnotách (`INVALID_INTENT`, `INVALID_LIMIT`, resp. `INVALID_CURSOR`). Chybové odpovědi obsahují pouze kód, nikoli text dotazu. Limit omezuje zpracování na úrovni API, ale nezastupuje limit celé URL na proxy/platformě, rate limiting ani ochranu proti mnoha samostatným požadavkům. Neznámé parametry pod touto hranicí zůstávají ignorovány.

## Release gates
MVP: secure HTTP, RAW integrity, validation, dependency scanning, least-privilege CI.
Beta: authorization tests, CSP/headers, parser hardening, abuse tests, share/privacy review.
v1.0: manual security review, supply-chain audit, incident exercise, backup/restore verification.

## Incident principle
Při nejistotě preferujeme nedostupnost nové informace před publikací potenciálně chybného nebo podvrženého dotačního údaje.
