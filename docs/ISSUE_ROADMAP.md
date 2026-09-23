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
