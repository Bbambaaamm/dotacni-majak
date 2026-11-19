# Project Watch: published-call path (#509)

The existing no-result action saves an anonymous project and enables its PROJECT
watch. The owner capability remains in session storage and is never placed in a
URL or an outbox payload. `/api/projects/:id/notifications` requires that
capability, returns only the project's in-app rows, and sends `no-store`.
The project page offers an explicit refresh and a call-detail deep link. It does
not present a topical match as eligibility or financing approval.

`PersistentProjectWatchConsumer` processes only the trusted publisher's
`CHANGE_DETECTION_REQUIRED` events and its own `WATCH_REEVALUATION_REQUIRED`
and `NOTIFICATION_REQUIRED` events in the D1-compatible SQLite outbox. Other
outbox types remain for their designated consumers. The published version must
be current, indexed, active, and attached to an OFFICIAL source. Safe
FTS token coverage feeds the existing HybridRanker; weak partial matches do
not meet the default POSSIBLE watch threshold. This is **topical** retrieval,
not an eligibility assessment. Missing eligibility and finance evaluations
become `NEEDS_INFORMATION` in the existing matcher and notification composer.
No web push or email is sent. Writes and outbox
acknowledgments are transactional and deduplicated; failed events retain a retryable
FAILED event without changing canonical last-known-good data. The in-app
center omits notifications for superseded versions and respects a disabled
watch for future delivery.

Local browser evidence: run `npm run web:e2e` with the documented Playwright
libraries. The added scenario saves a real watch through the Worker, publishes
an **explicitly simulated** official-style JSON record to immutable RAW via
`TrustedGrantIngestor`/canonical staging, projects search, consumes the actual
outbox through matcher/composer, checks owner-only notification, follows the
call's source link, and passes a mismatched RAW hash to the trusted ingest
boundary to verify the failed refresh leaves canonical version, outbox count,
and notification unchanged. The `example.invalid` source is a test fixture,
never a live official source. Expired PROCESSING leases are recovered (unit
regression test); unexpired leases remain owned by their worker.

Limitations: the consumer is a bounded offline SQLite worker, not yet scheduled
for production D1 transport; production `/api/*` routing or an explicit
`VITE_API_BASE_URL` must be provisioned before deployment (the test uses Vite's
local proxy). FTS-only token coverage can miss semantically related calls; the
score is a deterministic retrieval signal, not a calibrated probability. No
push or delivery preference UI exists here.
