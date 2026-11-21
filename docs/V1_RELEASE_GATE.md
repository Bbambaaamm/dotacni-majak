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
- CodeQL SAST scan acceptable (žádná nová findings v scope, nebo všechny findings recenzované a accepted v SARIF baseline),
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

## CodeQL SAST gate

Workflow `.github/workflows/codeql.yml` spouští GitHub CodeQL na push/PR do `main`
i týdně na `ubuntu-latest`, analyzuje `javascript-typescript` + `python` a
používá `security-extended` query suite podle `.github/codeql-config.yml`.

**Baseline policy:**
- Konfigurační soubor `.github/codeql-config.yml` definuje scope (aplikace, source
  SDK, ingestion pipeline, konektory, doméní balíčky) a exclusions (transients,
  worktrees, golden fixtures, E2E data, generované soubory, scripts, release data,
  migrace, data, research). Exclusio je pro generovaná/transient/test data, ne pro
  maskování neopravených findings v reálném kódu.
- `query-ignore` je zatím prázdný — žádná před-seed suppression bez recenzovaných
  findings. Každý query suppression musí přijít PRem s justifikací (false positive,
  accepted risk s expirací, detector limitace) a odkazem na tuto konfiguraci.
- Po prvním úspěšném CodeQL run na main se vytvoří SARIF baseline známých accepted
  findings. Až po ní se workflow hejguje jen na nová findings; starší accepted
  findings jsou surfaced jako informational. Předtím selže na libovolné finding v
  scope (fail-closed).

**Fail-closed:** workflow nemá `continue-on-error: true`. Jakékoli finding v scope
(před baseline) failuje PR. CodeQL action infrastrukturní selhání též failuje closed
— degradace na "skip security scan" není bezpečná.

**Secrets/PII:** workflow neexponuje secrets, ne loguje tokeny, ne loguje výsledky
s PII. Výsledky jsou SARIF uploadnuty do GitHub security tab. Config a workflow jsou
testovány na absence secret references v ne-komentářových řádcích přes
`tests/python/test_sast_workflow_contract.py`.

**Residual risk:** CodeQL zachycí statické patterns, nikoliv runtime abuse, business
logic vulns, za-running napadení. Manual `security_threat_review` (v1 gate manual item)
zůstává.

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
