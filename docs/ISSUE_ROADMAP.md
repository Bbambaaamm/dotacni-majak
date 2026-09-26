# GitHub Issue Roadmap

GitHub connector použitý při inicializaci neumí vytvářet Milestones ani Project board fields, proto jsou fáze explicitně zakódované v názvech issues a této mapě. Jakmile je Project board dostupný, tato data jsou zdrojem pro jeho naplnění.

## M0 — Product & Architecture Foundation
- #1 Foundation: monorepo, canonical contracts a CI
- #2 Licence, governance a contribution model
- #3 Brand assets, doména a name-collision research

## M1 — Canonical Schema & Source SDK
- #4 Canonical schema core domény
- #5 D1 migrations
- #6 TypeScript/Python contract sync
- #7 Attribute Registry a eligibility DSL schema

## M2 — Ingestion Foundation
- #8 GuardedHttpClient
- #9 RAW snapshot storage
- #10 Idempotent ingestion orchestrator
- #11 Data quality gate, quarantine, outbox

## M3 — First Searchable Sources
- #12 Retrieval research prvních zdrojů
- #13 EU Funding & Tenders
- #14 DotaceEU
- #15 JDP
- #16 NSA
- #17 SFŽP

## M4 — Ontology & Hybrid Search
- #18 Ontologie v1
- #19 FTS5
- #20 Semantic SearchProfile/vector budget
- #21 Hybrid ranking/explainability
- #22 Golden dataset / tenisové kurty

## M5 — Applicant & Eligibility
- #23 Applicant Profile
- #24 Progressive profiling
- #25 Eligibility evaluator

## M6 — Finance
- #26 Finance engine

## M7 — Czech National Coverage
- #42 OP TAK/API
- #43 IROP/CRR
- #44 MPSV
- #45 MŠMT/OP JAK
- #46 Ministerstvo kultury
- #47 MMR
- #48 MZe/SZIF
- #49 TAČR
- #50 NRB
- #51 DZS/Erasmus+

## M8 — Regional Coverage
- #62–#75: Praha + všech 13 krajů, samostatně

## M10 — Change Detection & Monitoring
- #27 ChangeEvent diff
- #28 Source Health/watchdog

## M11 — Watches & Notifications
- #29 Project Watch matcher
- #30 Notification outbox/Web Push

## M12 — Application Workspace & Decision Support
- #31 Workspace/readiness
- #53 Porovnání
- #54 PDF export
- #55 Read-only share

## M13 — Historical Intelligence
- #36 Historical domain
- #52 ReD/MONITOR connector

## M14 — UX/UI & Accessibility
- #32 Web/PWA foundation
- #33 Homepage
- #34 Results/detail
- #35 Accessibility harness
- #56 Relevance feedback
- #57 Navrhnout zdroj
- #58 Public changelog
- #59 No-result/ineligible/UNKNOWN UX

## M15 — Security & Privacy
- #37 Threat model/privacy
- #61 Document security

## M16 — Production & Reliability
- #38 Cloudflare deployment
- #39 UsageBudgetManager
- #60 Source Coverage page

## M17 — Public Beta
- #40 Beta/usability research

## M18 — v1.0
- #41 Production readiness gate

## Critical path
#1 → #4 → #5/#6/#7 → #8/#9 → #10 → #11 → #12 → first connectors → #18/#19/#20/#21 → #23/#25 → #26 → #29/#30 → #31 → #40 → #41

## Paralelní proudy po foundation
- Data contracts: #4–#7
- Secure ingestion: #8–#11
- UX foundation: #32/#35
- Brand/governance: #2/#3


## Current execution policy — audit 2026-09-26

Milestone prefixes `M0–M18` describe **product area / maturity**, not a license
to execute work in numeric order. Agents MUST choose the next task by:

1. unresolved **P0 dependency** on the user-visible critical path,
2. data accuracy / provenance / safety,
3. end-to-end functionality,
4. only then breadth, polish and release hardening.

Do not start a later-surface task merely because its issue is newer or more
recently updated.

### Canonical near-term P0 path

The current backend trust gap is:

`#533 → #535/#536/#537 → #534 → #572 → #508`

- **#533** canonical staging before publish gate,
- **#535** SourceRecord identity/change detection,
- **#536** immutable DocumentVersion publication,
- **#537** FieldEvidence persistence/integrity,
- **#534** atomic canonical version + evidence + outbox publication,
- **#572** real connector → canonical → search backend E2E,
- **#508** browser E2E: intent → results → detail → provenance.

Items that do not unblock this path should not pre-empt it unless they fix a
security/data-loss regression or CI failure.

### Duplicate policy

One implementation goal must have one open canonical tracker. During the
2026-09-26 audit, older duplicate copies `#523–#528, #530–#532` were closed
in favor of `#533–#538, #540–#542` respectively. Before opening a new issue,
search open issues by exact goal/title and link/close duplicates.

### MVP proof rule

A feature is not considered end-to-end complete merely because UI, API and
connector components exist independently. For the core `Najde` flow, completion
requires deterministic evidence that:

`official source → RAW → normalized/staged → canonical + provenance → search → detail → official evidence`

works without hardcoded demo data, and a browser-level regression covers the
user journey.
