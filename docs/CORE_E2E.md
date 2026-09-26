# Core full-stack browser E2E

Issue #508 is verified against a real local stack:

- Vite web server with the normal /api proxy,
- Wrangler Worker API,
- isolated local D1 with the complete migration chain,
- deterministic E2E seed data,
- Chromium Playwright.

The browser does not mock successful search/detail API calls.

Covered flows:

1. non-sport intent -> two active results -> status/provider result-set filters ->
   grant detail -> official source -> concrete FieldEvidence,
2. tennis-court reconstruction -> CLOSED historical NSA-style record is not
   surfaced as active -> Project Watch CTA,
3. search backend failure -> fail-closed error state with no invented results.

The seed is explicitly synthetic E2E data. Real connector/source correctness is
proven separately by #572 using the actual NSA and EU Funding & Tenders
adapters, RAW snapshots and official-contract fixtures.

Filter note: this test covers bounded filtering of the currently loaded result
set. Full API facet counts/performance remain independently tracked by #290.
