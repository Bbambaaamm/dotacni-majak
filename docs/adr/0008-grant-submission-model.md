# ADR-0008: Modelování submission/Application informací pro GrantCallVersion

## Status
Proposed (čeká na review).

## Context
Issue #576 (M1, data/grant) vyžadovala ukládat praktické informace nutné k
podání žádosti: portal URL, application method, account/signature requirements
(if explicit) a provider contacts (name/role/email/phone, when public), se
všemi evidence/UNKNOWN.

Na `main` už má tabulka `grant_call_versions` sloupec `application_url`, ale
není součástí kanonického v1 schéma (`grant-call-version.schema.json`) ani
`GrantCallVersionRecord`, a nepokryvá method/contacts/requirements ani
provenance. #573 (`grant_evaluation_criteria`) ukázal preferential pattern:
kritická podstatnání jsou modelována jako **samostatná entita + tabulka** s
`evidence_id`, `completeness_status` a `verification_status` — odděleně od
holistického `verification_status` verze — a **bez ingestion wiring** (repository
i publisher nepřidávají kritéria; tabulka je model-only až do M3 ingestion slice).

## Decision
1. Vytvořit novou kanontickou entitu `GrantSubmission` jako **1:1** k
   `grant_call_versions` (UNIQUE FK na `grant_call_version_id`), nikoli rozšířit
   `grant_call_versions` inline.
   - Důvod: izoluje provenance/úplnost submission informací od verze; sleduje
     #573 pattern; nezkoumává žádný existující repository/publisher/record
     (bounded M1 slice, žádné ingestion wiring).
2. Pole (všechna podmíněná = nullable, kromě identity/provenance):
   `portalUrl`, `applicationMethod` (enum), `accountRequirement`,
   `signatureRequirement`, `contactName`, `contactRole`, `contactEmail`,
   `contactPhone`, `evidenceId`, `completenessStatus`, `verificationStatus`.
3. `applicationMethod` je uzavřený enum (`ELECTRONIC`/`PAPER`/`HYBRID`/`EMAIL`/
   `POSTAL`/`OTHER`) — ne volný text ani „šance.“
4. Absence řádku == `UNKNOWN` (žádné fake positive; nevyžadovalo se).
5. Změna je ekvivalentní #573: schema + migration + fixture + schema/migration
   testy. Ingeste/normalizace/publisher jsou výsledkem pozdějšího slice (M3).

## Consequences
- Kladné: jednoduchý, reviewovatelný, testable model-first slice; zachovává
  `UNKNOWN != FAIL`, `relevance != eligibility`, immutable versioning, RAW-first.
- Záporu: legacy sloupec `grant_call_versions.application_url` zůstává
  nezměněn (deprecován v pozdějším ingestion slice); multiple contacts (seznam)
  je modelován jako jeden primární kontakt — multi-contact list je follow-up.
