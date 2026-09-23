# v1.0 production readiness gate

Issue: #41

v1.0 znamená důvěryhodnou veřejnou službu, ne jen dokončený feature backlog.

## Automatické gatey

Před v1.0 musí být pro konkrétní release commit doloženo:

- CI green,
- canonical schema + migration compatibility green,
- unit/integration/E2E regression green,
- search golden dataset green,
- eligibility truth tables green,
- finance regression green,
- connector contract tests green,
- source live smokes ve stavu odpovídajícím deklarovanému coverage,
- accessibility automation green,
- production build/dry-run green,
- dependency/security scan bez neakceptovaných critical findings,
- UsageBudgetManager pod definovanou bezpečnostní hranicí nebo s otestovanou degradací.

## Manuální / review gatey

Automatizace nestačí. Vyžadujeme:

- Public Beta usability evidence z Issue #40,
- keyboard-only audit,
- screen-reader audit klíčových toků,
- mobile + 200% zoom/reflow audit,
- privacy review,
- threat model/security review,
- source coverage audit,
- provenance spot-check,
- recovery/runbook tabletop,
- záloha/export/restore ověření,
- transparentní seznam známých omezení,
- licence/governance review,
- incident/contact cesta.

## Source coverage audit

Pro každý zdroj musí být doloženo:
- authority,
- retrieval method,
- explicitní coverage boundary,
- last successful check,
- expected refresh cadence,
- disappearance policy,
- health status,
- známé omezení.

LIMITED/DEGRADED zdroj není automatický blocker v1.0, pokud je stav veřejně
pravdivě komunikován a produkt netvrdí širší pokrytí.

## Security gate

Nelze vydat v1.0 s:
- známým kritickým IDOR,
- raw capability/share token loggingem,
- nezabezpečeným SSRF path,
- neomezeným file parsingem,
- automatickým placeným upgrade,
- veřejným citlivým project/applicant payloadem,
- nevyřešenou critical dependency vulnerability bez explicitního risk acceptance.

## Data quality gate

Nelze vydat v1.0, pokud:
- parser failure může provést destructive reconciliation,
- disappearance může bez důkazu změnit status na CLOSED/CANCELLED,
- kritická finance/eligibility tvrzení nemají provenance nebo UNKNOWN handling,
- search relevance je prezentována jako probability of success.

## Release evidence

Každé v1.0 gate rozhodnutí musí mít datum, release SHA a odkaz na evidence.
Issue #41 se neuzavírá pouze tímto dokumentem; uzavírá se až po skutečném auditu
konkrétní produkční kandidátní verze.


## Evidence workflow

1. Copy `release/v1-evidence.example.json` to `release/v1-evidence.json` for a
   concrete release candidate.
2. Set the exact 40-character release commit SHA.
3. Link evidence for every automated and manual check.
4. Complete Public Beta gate (#40) before marking `manual.betaUsability=PASS`.
5. Run the recovery scenarios from `docs/RUNBOOK.md`.
6. Publicly disclose and explicitly accept every known limitation retained for
   release.
7. A human reviewer sets `decision.status=GO`, date, reviewer and rationale.
8. Run the manual GitHub Action **v1.0 Release Gate**.

The validator intentionally refuses to infer PASS from the existence of a
document or from automated tests alone.
