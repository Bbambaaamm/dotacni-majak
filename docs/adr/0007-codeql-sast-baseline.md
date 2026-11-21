# ADR-0007: CodeQL SAST workflow a bezpečnostní baseline policy

## Status
Accepted

## Context
M15 / GitHub issue #427 — automaticky analyzovat TypeScript/Python bezpečnostní chyby pomocí GitHub CodeQL, s jasně definovanou baseline, suppressive policy, fail-closed chováním a release gate integrací.

Existující `.github/workflows/codeql.yml` spouští CodeQL na push/PR do main a týdenně, analyzuje `javascript-typescript` + `python` a používá `security-extended` query suite. Chybí však:
- konfigurační soubor s path coverage a exclusion policy,
- dokumentovaná baseline/suppression policy,
- fail-closed definice pro degraded stav,
- integrace do v1.0 release gate.

## Decision
1. **CodeQL konfigurace** — `.github/codeql-config.yml` definuje co se skenuje (aplikace, source SDK, ingestion pipeline, konektory, doménní balíčky) a co se excluduje (node_modules, __pycache__, worktrees, golden fixtures, E2E data, generované soubory, scripts, release evidence, migrace, data, research). Exclusio je pro generovaná/transient/test data, nikoliv pro maskování neopravených findings v reálném kódu.

2. **Baseline / suppression policy** — `query-ignore` je zatím prázdný. Nemá smysl zakládat před-seed ignoring bez recenzovaných findings. Každý query suppression musí přijít PRem s dokumentovanou justifikací (false positive, accepted risk s expirací, nebo detector limitace) a odkazem na tuto konfiguraci. Po prvním úspěšném CodeQL run na main se vytvoří SARIF baseline známých accepted findings; až po ní se workflow hejguje jen na nová findings, starší accepted findings jsou surfaced jako informational.

3. **Fail-closed** — workflow je fail-closed: žádný `continue-on-error: true`. Jakékoli finding v scope (před baseline) means PR failuje. Po publikaci baseline se selže jen na NOVA findings. Bezpečný degraded stav: pokud CodeQL action selže na infrastrukturní úrovni (cache, action unavailable), workflow selže closed — nemá smysl degradovat na "skipping security scan".

4. **Log redaction / secrets** — CodeQL výstup je SARIF uploadnutý do GitHub security tab. Workflow neexponuje secrets, ne loguje tokeny, ne loguje výsledky s PII. Config a workflow jsou testovány na absence secret references v ne-komentářových řádcích.

5. **Release gate** — `v1-gate.json` získává `security_sast_scan_acceptable` v automated gates. Release candidate musí dokumentovat, že CodeQL scan je acceptable (žádná nová findings v scope, nebo všechny findings recenzované a accepted v baseline). To je součást `accepted_risks` evidence v rámci `releaseEvidence`.

6. **Runbook/dokumentace** — `docs/V1_RELEASE_GATE.md` a root `SECURITY.md` jsou aktualizovány o SAST workflow popis, a `docs/adr/0007-codeql-sast-baseline.md` dokumentuje tuto rozhodnutí.

## Consequences
- Každý PR touch application code se očekává bez new findings v scope pro v1.0 gate.
- První CodeQL run na main vytvoří SARIF baseline, která musí být recenzovaná před produktivním nasazením.
- Exclusion policy je transparentní a auditovatelná; no exclusion masks unfixed real vulns.
- Workflow je testovatelný: `tests/python/test_sast_workflow_contract.py` validuje strukturu workflow + config bez PyYAML dependency.
- Residual risk: CodeQL není magická solution; zachycí statické patterns, nikoliv runtime abuse, business logic vulns, ani za-running napadení. Manual security review (v1 gate manual item `security_threat_review`) zůstává.
