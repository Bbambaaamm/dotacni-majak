# MVP / Beta readiness audit — 2026-09-26

This snapshot separates **proven in the running stack**, **implemented but not
yet the default/product path**, and **blocking public Beta**. Milestone labels
remain taxonomy; this document is an execution/readiness view.

## 1. Proven end-to-end now

### Najde — core search journey

Merged #508/#638 proves in CI with real local services:

- Vite web,
- normal `/api` proxy,
- Wrangler Worker,
- fully migrated isolated D1,
- Chromium Playwright,
- intent → search → results → bounded result-set filter → grant detail,
- source link and concrete FieldEvidence,
- UNKNOWN eligibility copy,
- no-result → Project Watch CTA,
- search 503 → fail-closed UX with no invented results.

Successful search/detail requests are not browser mocked.

### Trusted connector/backend path

Merged #572/#637 proves both distinct source paths with the real adapter code
and checked-in sanitized official-contract fixtures:

- NSA HTML,
- EU Funding & Tenders JSON/API,
- GuardedHttpClient,
- RAW snapshot,
- normalizer,
- SourceRecord NEW/CHANGED/NOT_MODIFIED,
- immutable DocumentVersion,
- canonical staging,
- atomic GrantCallVersion + FieldEvidence + outbox,
- search projection / FTS.

The CLOSED NSA 16/2026 fixture remains auditable but is not an active search
result. The EU F&T OPEN fixture is searchable.

### Canonical trust boundary

Merged #533/#535/#536/#537/#534 proves:

- staging before canonical publish,
- source-content identity/change detection,
- immutable document versions,
- validated evidence references,
- atomic canonical + evidence + outbox publication,
- rollback on evidence/outbox failure,
- idempotent retry.

## 2. Implemented / technically prepared, but not yet the default complete product path

### Default live/local refresh still uses legacy direct publish — P0

Issue #639. `scripts/local_refresh_data.mjs` still invokes
`local_ingest_*.py` → `render_import_sql` from `local_publish.py`.
The trusted path above is proven and reusable, but it is not yet the default
refresh publisher.

Do not call public ingestion provenance-complete until #639 is closed.

### Pohlídá

Project Watch CRUD/API, matcher and notification/outbox domain pieces exist.
The complete no-result → saved watch → newly published call → match →
notification/deep-link journey is not yet browser-E2E proven (#509).

### Applicant / eligibility

Applicant/profile and deterministic eligibility domains exist. The product still
needs the complete UNKNOWN → progressive question → reevaluation journey (#510)
plus its final onboarding/detail integration (#402/#401).

### Finance

The deterministic finance engine exists, but full public API/UI integration
and boundary/property proof remain tracked (notably #309/#310/#311). A search
or detail page must not imply finance completeness merely because the engine
package exists.

### Dotáhne / Workspace

Workspace/readiness domain and some sharing/capability plumbing exist. The full
"Chci tuto dotaci" → workspace → checklist/Next Action → new grant version →
change diff journey is not yet proven (#511), and the main workspace UI remains
open (#404).

### Search/detail UX breadth

The current-result-set status/provider filter is real and browser tested.
Complete facets, API counts/performance are still #290; sorting, pagination,
mobile filter dialog/chips remain in #400. Detail still needs final
eligibility/finance/Next Action integration in #401.

## 3. Public Beta blockers

### A — Data path / runtime

1. #639 — make trusted staging/publisher the default refresh path.
2. #445 — production R2 RawSnapshotStore with immutable semantics.
3. #443/#444/#452 — environment/config/staging deployment reproducibility.

### B — Three product promises

1. **Najde:** finish #400/#401 and search-quality/data audits.
2. **Pohlídá:** #509.
3. **Dotáhne:** #402/#403/#404, #510/#511 and finance integration.

### C — Security/privacy release gate

Before public Beta, at minimum:

- #421 API input validation,
- #422 abuse/rate controls,
- #423 authorization/IDOR regression,
- #424 browser security headers/CSP,
- #431 privacy inventory/retention/deletion matrix,
- #440 structured OWASP ASVS/API review.

### D — Beta evidence

- #477 Beta entry criteria / feature freeze,
- #482 manual accessibility audit,
- #484 manual active-grant data-quality audit,
- #485 human search relevance evaluation,
- #486 Beta security review / bug bash.

## 4. New execution path after the core Najde proof

Highest-priority default order:

`#639`
→ product-path completion in parallel
  (`#400/#401`, `#402/#510`, `#403/#509`, `#404/#511`)
→ finance/API completion
→ security/privacy gates
→ staging/production infrastructure
→ manual Beta evidence / entry gate.

A later milestone must not pre-empt an unresolved P0 dependency merely because
its issue number is newer.

## 5. What "MVP complete" means from now on

For each promise, completion requires a browser-visible proof, not only a
package/module:

- **Najde:** proven.
- **Pohlídá:** not proven until #509.
- **Dotáhne:** not proven until #511.
- Trusted live ingestion: not default until #639.

This prevents technical foundations from being reported as finished
user-facing behavior.
