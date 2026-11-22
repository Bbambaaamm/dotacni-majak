# Finance scenario selection — bounded #304 slice

## Current D1 rule/scenario provenance gate

`apps/api/src/financeProvenance.ts` exposes a read-only `verifyFinanceRuleProvenance` gate. A single D1 batch anchors the current call version, one COMPLETE/VERIFIED rule set, its connected groups and conditions, and version-linked scenarios. Every condition and scenario needs VERIFIED `field_evidence` with an exact version/field path (`/rule_conditions/{id}` or `/funding_scenarios/{id}`), an EXTRACTED document version associated with the same grant call, and an OFFICIAL or OFFICIAL_OPEN_DATA source. The gate also loads each condition's joined attribute definition and operand from the same snapshot; only active applicant scalar definitions with a supported deterministic operator and correctly typed/bounded JSON operand are certified. Unsupported project rules, inactive definitions and malformed operands remain NEEDS_INFORMATION with no scenario/evidence IDs, even if the linked source is official. Missing, partial, cross-version, unrelated or quarantined evidence is not certified; bounded real-D1 tests cover those cases. This is a provenance/operand-shape check only: it does not bind a source document's contents to the expected operand, load applicant values, invoke the finance selector, authenticate applicant ownership or prove the value binding/freshness of a verified applicant attribute. An existing generic `/eligibility` evidence path does not satisfy per-condition evidence. Therefore even the positive `STRUCTURE_ONLY` result reports only bounded rule shape and matching official evidence references, **not** verified rule-group meaning, eligibility PASS or an authorization to show personalized amounts. The gate never emits a semantic `VERIFIED` verdict; changing AND to NOT without a corresponding source-content binding remains structure-only. No public API calls this gate yet.

## Rule-tree structural safety (follow-up)

The same read-only D1 gate also checks the actual group operator and direct child count against the deterministic evaluator: AND/OR groups must be nonempty; NOT has exactly one direct group or condition child; nested groups must fit the evaluator's 16-level bound. A disconnected/cyclic graph is an error; unsupported but connected structure remains `NEEDS_INFORMATION` with no scenario or evidence IDs. Real-D1 regressions cover invalid NOT arity and empty groups. This does not attest that source text semantically equals the operand; it neither verifies applicant ownership/value freshness nor enables personalized finance/API/UI amounts.

## Verified input boundary (follow-up)

`apps/api/src/financeApplicantPreflight.ts` now provides an API-internal, read-only
`preflightFinanceApplicantValues` check for the sparse `applicant_attribute_values` table.
Rejected or incomplete two-query D1 snapshots are `ERROR / SNAPSHOT_READ_FAILED`
with no profile, value or evidence IDs; they are not mistaken for an unowned
profile or absent values. The caller supplies an already authenticated principal, an exact profile ID, and an
`asOf` UTC instant. One D1 batch checks profile ownership and at most 128 value rows
from the same snapshot. Each row must have an active applicant scalar definition,
matching and well-formed byte-bounded JSON type (including rejection of embedded NUL), VERIFIED official-source status, and
VERIFIED evidence on that exact value ID and attribute key from an EXTRACTED official
document. Claimed ARES/CZSO kinds must also match the configured `ARES_PROFILE` /
`CZSO_POPULATION` registry codes (see `data/sources`); OTHER_OFFICIAL requires
an official registry authority but has no more specific identity binding.
Missing or inconsistent profile creation, source first-seen, observation, evidence,
document retrieval or verification timestamps fail closed. When the owned profile has a
non-null IČO or municipality code, the corresponding sparse official value must agree
with it in the same D1 snapshot; conflicting values withhold all IDs and return
`NEEDS_INFORMATION / PROFILE_ATTRIBUTE_CONFLICT`. Null profile fields remain unknown,
not a claimed match. This consistency check does not authenticate source text.
`asOf` is an upper consistency bound; there is
no hard-coded maximum age or proven freshness policy. On success the result is
`STRUCTURE_ONLY` with profile, value, and evidence IDs only. Failed checks release
no value or evidence IDs. It never returns applicant values, a semantic `VERIFIED`
verdict, selection, or amount, and it is not wired to a public endpoint or the
finance selector. Document evidence metadata does not prove that the document text
actually matches a stored value. A trusted resolver, source-content/value binding,
explicit freshness policy, and composition with the version-bound rule/scenario
gate remain prerequisites for personalized finance results.

`select_from_eligibility` takes `inputs` keyed by attribute key, each an `ApplicantInput(value, source_kind, verification_status, evidence_id)`, rather than accepting bare values. It evaluates only explicitly VERIFIED ARES/CZSO/OTHER_OFFICIAL inputs with nonblank evidence references. User declarations, derived values, missing evidence and partial verification are omitted and yield UNKNOWN, not a false PASS or FAIL. Its result carries separate rule and input evidence IDs per group; it never returns applicant values. Tests cover both raw passing and failing declarations, missing and independent condition evidence. This is still a domain contract, **not** a D1 trust decision: the future loader must prove evidence entity/field, official source/document status, version membership, applicant ownership, value binding and freshness in one consistent read before invoking it. No personalized amount or API is enabled by this change.

The canonical `FundingScenario.conditionGroupId` refers to an eligibility condition group. The finance engine does not evaluate rules or infer applicant/project attributes: the caller supplies already evaluated `ScenarioApplicability` values for each linked group, keyed by group ID. Those results must come from the deterministic eligibility evaluator and retain the underlying rule/field evidence in the upstream response. A missing group result is UNKNOWN, never PASS or FAIL. Scenarios without a linked group retain their explicit applicability (legacy callers default to PASS); callers must not use that default to claim an unverified applicant-specific condition.

`FinanceEngine.select_scenario(scenarios, group_results=...)` returns a scenario only if exactly one is PASS and every other scenario is FAIL. One PASS plus any UNKNOWN remains `NEEDS_INFORMATION`, as do multiple PASS scenarios. No automatic choice of the highest support rate. Duplicate IDs or invalid result values return ERROR. A linked scenario cannot be calculated by `evaluate` unless its condition group result is explicitly PASS; FAIL/UNKNOWN/missing values produce no grant/cash amount. `evaluate` still checks cost bounds, payment mode and instrument separately.

The Python domain contract is separate from the D1/API/UI surface. The eligibility evaluator now emits post-order `group_results` with group ID, raw PASS/FAIL/UNKNOWN/ERROR/NOT_APPLICABLE and descendant condition IDs; duplicate or empty group IDs fail closed without group outputs. A raw group outcome is **not** finance applicability by itself: consumers must verify matching grant-call version/rule-set identity, completeness, verification and provenance, handle ERROR/NOT_APPLICABLE safely and never treat missing groups as PASS. `select_from_eligibility` is a bounded in-memory bridge: it evaluates the actual rule tree, requires matching caller-supplied immutable version IDs, COMPLETE/VERIFIED rule metadata, VERIFIED descendant conditions and nonblank per-condition `field_evidence` IDs before mapping a group to PASS/FAIL. Missing/partial/unverified evidence, unknown groups and unlinked scenarios remain UNKNOWN; a stored scenario FAIL cannot exclude a competitor without a verified group FAIL. Any descendant condition ERROR (even under an OR root that passes), malformed rule evaluation or version mismatch is ERROR. It returns the selected scenario and group evidence references, **not** a financial amount. The trusted D1 loader must still authenticate that every scenario, rule, condition and evidence ID belongs to that exact canonical version; caller-supplied IDs alone are not proof of provenance. Do not expose personalized finance amounts until that loader, explicit finance-input provenance and API/browser tests are implemented. The grant detail API exposes the stored `conditionGroupId` for each version-linked funding scenario; the detail UI labels linked conditions as UNKNOWN pending actual rule evaluation, and makes no applicability claim for unlinked scenarios. It does not pass applicant data or calculate support. No application success prediction follows from selection; official programme rules remain authoritative. No new personal profile data, retention, dependency or paid provider is introduced here.
