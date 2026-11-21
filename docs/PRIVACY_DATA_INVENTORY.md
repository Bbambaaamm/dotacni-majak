# Privacy Data Inventory, Purpose, Retention & Deletion Matrix

Issue: #431 (M15 · Privacy data inventory, purpose, retention a deletion matrix)
Dependency: #37 (Threat model, privacy architecture — closed)

This document is the human-readable counterpart of the machine-readable
manifest at `data/privacy/data_inventory.json`. The manifest is validated
continuously by `tests/python/test_privacy_data_inventory.py` against the live
canonical schema in `migrations/` and the API SQL source in `apps/api/src/`.

## Status legend

- **proposed_pre_beta** — retention/deletion parameters proposed here; must be
  accepted by a human reviewer at the Privacy gate before Public Beta (#40).
  The inventory *structure* (what exists, where) is verified automatically;
  the *retention numbers* are policy and require explicit sign-off.

## Principles (from docs/PRIVACY.md, ADR-0007)

1. Collect only data necessary to find, evaluate and track a grant.
2. First search works without registration; accounts are attached only on
   synchronisation/share/watch actions.
3. Capability tokens (owner + read-only share) are stored **only as a
   domain-separated SHA-256 hash** — raw tokens are never persisted or logged.
4. Read-only share is a strict allowlist projection; it never discloses
   `owner_user_id`, `applicant_profile_id`, internal notes, document storage
   refs, watch or account data.
5. `UNKNOWN != FAIL` — ambiguous source truth does not block eligibility or
   trigger destructive changes.
6. Fail-closed on source degradation: preserve last-known-good, block
   destructive reconciliation.
7. Zero-cost / no implicit collection: analytics collection is never
   auto-activated; a failed push subscription degrades silently to in-app.

## Data inventory matrix

| # | Data category | Store (table / location) | PII classification | Purpose | Retention | Delete / Export | Fail-closed / degraded |
|---|---|---|---|---|---|---|---|
| 1 | Applicant profile | `applicant_profiles`, `applicant_attribute_values` | PII — IČO, org name, legal form, municipality, region, size, VAT status, dynamic attributes | Eligibility matching (geography, type, size) | user-controlled — until deletion requested | Export via account data export; delete via account deletion (cascades to attribute values) | Attributes fetched from official registries (ARES/CZSO) only on explicit user action; UNKNOWN verification_status does not block eligibility |
| 2 | Project | `projects` | PII-high-risk — free-text `natural_language_intent`, `title`, `applicant_profile_id`, `owner_user_id` | Grant matching, readiness, application prep | user-controlled — no scheduled purge of intent; exportable in full | Owner capability gate. `natural_language_intent` never sent to AI providers without explicit purpose | Anonymous projects (`anonymous:{projectId}`) remain manageable via capability token; project text never becomes canonical fact about a grant |
| 3 | Watches | `watches`, `watch_matches` | PII — `user_id`, `filter_json` (may contain search terms) | Grant change monitoring + notification trigger | until watch deleted (DELETE `/projects/:id/watch`) | watch_matches cascade on deletion | Disabled/revoked watch produces no notifications; watch requires owner capability; no public listing |
| 4 | Push endpoints | `web_push_subscriptions` | PII-sensitive — `user_id`; encrypted `endpoint_ciphertext`, `p256dh_ciphertext`, `auth_ciphertext` | Web push delivery | until unsubscribe / revoke | Revoked on unsubscribe; inactive revoked rows purged 30 days later | Opt-in, rate-limited; failed push degrades silently to in-app notification |
| 5 | Notifications | `notifications` | PII — `user_id`, `title`, `body` (may echo grant/project text) | Delivery of change & deadline alerts | 90 days | Tied to user identity; deleted/anonymised on account deletion | Outbox at-least-once with `dedupe_key`; idempotent handlers |
| 6 | Logs & audit | `outbox_events`, `change_events`, `source_runs`, `source_records`, `ingestion_runs`, `scheduler_watchdog_events`, `source_health`, `project_owner_audit_events`, `share_audit_events`, `relevance_feedback` | operational / security — audit events carry `user_id`/`actor_user_id` only as attribution; **no raw capability or share tokens** | Security audit trail, ingestion provenance, operational debugging | security/audit: 1 year; operational: 90 days | System-managed, not user-exportable; audit logs may be retained longer for incident response | Source/parser failure → DEGRADED, preserve last-known-good, block destructive reconciliation |
| 7 | Project capabilities | `project_owner_capabilities`, `project_share_links` | secrets — **hash only, no raw token** | Owner authz + revocable read-only share | retained with project; share links expire (default 30d, max 365d); revoked/expired hashes purged 30 days later | Not user-exportable; revocation immediate & idempotent | Missing/invalid token → 404 without disclosing project existence |
| 8 | Uploads | `workspace_documents` + R2 object store | user content — `filename` may contain PII; `storage_ref` opaque key | Application/requirement documents for workspace readiness | retained with workspace; purged 30 days after project deletion | Owner capability gate; deleted with parent workspace | Documents MIME/size/validated, failures quarantine (no destructive change) |
| 9 | Analytics | (not implemented) Cloudflare `send_metrics=false`; in-memory `ResolverMetrics` ephemeral | anonymous telemetry (aggregate only) | (future) aggregate usage + source health | NOT persisted yet | N/A | Absence → zero telemetry, no implicit collection |

## Secrets / PII-not-in-logs invariants (automated checks)

`tests/python/test_privacy_data_inventory.py` asserts:

- `project_owner_capabilities` and `project_share_links` have a `token_hash`
  column and **no** `token` column (raw tokens never stored).
- Audit/log tables (`project_owner_audit_events`, `share_audit_events`,
  `outbox_events`, `change_events`, `source_runs`, `source_records`,
  `ingestion_runs`) have **no** `token` column (no raw tokens in logs).
- The share resolver SQL (`apps/api/src/share.ts`) selects **only** the
  whitelisted projection `{id, title, natural_language_intent, currency_code,
  estimated_total_budget_minor, planned_start, planned_end, updated_at}` —
  never `owner_user_id` or `applicant_profile_id`.
- Share responses carry `Cache-Control: private, no-store`,
  `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer`.
- Web-push subscription keys are stored as `*_ciphertext` only — no plaintext
  `endpoint` column.

These checks run in CI as part of `npm run test:python` (issue #431
contract) and **fail-closed**: any new column or resolver change that violates
an invariant breaks the build until the inventory is updated.

## Negative / abuse scenarios covered

| Scenario | Defence | Tested by |
|---|---|---|
| Unknown share token | collapsed to 404 `SHARE_NOT_FOUND` (no project disclosure) | `index.test.ts` "collapses malformed and unknown shares to 404" |
| Revoked / expired share | 404 without disclosure; separate audit event | `test_sharing.py` resolve revoked/expired/unknown |
| Owner-capability IDOR | token is project-scoped, not user-scoped; wrong project → 404 | `test_project_owner_capability.py` test_owner_token_is_project_scoped_against_idor |
| Token brute-force | 256-bit tokens, shape validation rejects short strings before DB lookup | `test_project_access.py` / `test_sharing.py` malformed-token tests |
| Share owner mismatch | `DENIED_OWNER_MISMATCH` audit, PermissionError | `test_sharing.py` create/revoke fails_when_not_owner |
| Revocation is idempotent | second revoke returns same `revoked_at` | `test_sharing.py` revoke_is_idempotent |
| Unknown share token in resolver | DB never touched (shape check first) | `index.test.ts` "DB should not be touched for malformed token" |
| Push subscription abuse | opt-in, rate limits, unsubscribe/revocation | design (see NOTIFICATIONS.md) |

## Fail-closed / safe degraded states

- **Source/parser failure**: affected source marked `DEGRADED`/`UNAVAILABLE`;
  last-known-good canonical data preserved; destructive reconciliation blocked
  (RUNBOOK §2).
- **Missing/invalid capability**: 404 without disclosing whether the project
  exists (non-disclosing).
- **Push delivery failure**: falls back to in-app notification; never escalates
  to email/SMS without explicit implementation.
- **Analytics absent**: zero telemetry, no implicit provider activation
  (ADR-0004 zero-cost-first).
- **Vector/semantic search exhaustion**: degrades to FTS + ontology +
  structured filters; canonical + eligibility remain functional (ARCHITECTURE).

## Release gate

- **Gate name**: Privacy gate — Public Beta (#40) pre-requisite.
- **Who**: independent security/privacy reviewer (human).
- **What must be green**: `npm run test:python` including
  `test_privacy_data_inventory.py` + `npm workspace @dotacni-majak/api test`.
- **What must be reviewed**: retention numbers in the matrix above (currently
  `proposed_pre_beta`); any change to capability/share storage or the share
  resolver projection.
- **Residual risks**: (see "Residual risks" below) — documented and accepted
  at this gate, not auto-closed.

## Residual risks (to be accepted at the privacy gate)

1. `natural_language_intent` is free-text and may contain PII; it is retained
   per-project and only purged on explicit user deletion. Mitigation: never sent
   to AI providers without explicit purpose (PRIVACY.md AI section); deterministic
   eligibility/finance fallback exists.
2. Push endpoint keys are encrypted at rest in D1; the encryption envelope
   lifecycle/keys are not yet rotated via a dedicated KMS. Mitigation: keys are
   per-subscription and revocable; scope limited to push delivery only.
3. Analytics is intentionally absent; any future implementation must preserve
   the aggregate-only/no-PII contract and the zero-cost fallback.
4. Operational log retention (90 days) vs. security audit retention (1 year)
   overlap is by design; operators must not cross-query them for profiling.

## Next action (continuation slices)

- Implement explicit user data export + deletion endpoints (DELETE
  `/projects/:id`, account data export) tied to owner capabilities.
- Add background retention sweeper for expired share hashes and old audit logs.
- Wire analytics collection (out of scope for this slice) with a separate
  privacy sub-issue and explicit consent design.
