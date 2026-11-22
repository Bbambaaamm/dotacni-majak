# Security Policy

## Reporting
Bezpečnostní zranitelnosti nehlaste veřejným issue, pokud by zveřejnění mohlo usnadnit zneužití.

Dokud nebude nakonfigurován dedikovaný security contact, použijte GitHub private vulnerability reporting, pokud je pro repository dostupný.

## Supported versions
Před v1.0 podporujeme aktuální main / poslední veřejný deployment.

## Public issues
Běžné chyby dat, UX a nebezpečnostní bugy lze hlásit standardním GitHub issue.

## Static analysis (SAST) workflow

Repository používá GitHub CodeQL pro automatickou statickou analýzu bezpečnostních
vzorů v TypeScript (web + API) a Python (source SDK, ingestion pipeline, konektory,
doméní balíčky).

- **Workflow:** `.github/workflows/codeql.yml` — spouští se na push/PR do `main` i
  týdně (cron `27 4 * * 3`), analyzuje `javascript-typescript` + `python` s
  `security-extended` query suite.
- **Konfigurace:** `.github/codeql-config.yml` — definuje co se skenuje (scope) a
  co se excluduje (transients, worktrees, golden fixtures, E2E data, generované
  soubory). Exclusio je pro generovaná/transient/test data, ne pro maskování
  neopravených findings v reálném kódu.
- **Baseline / suppression:** `query-ignore` je zatím prázdný. žádná před-seed
  suppression bez recenzovaných findings. Každý query suppression musí přijít PRem
  s justifikací (false positive, accepted risk s expirací, detector limitace).
  Po prvním úspěšném run na main se vytvoří SARIF baseline; až po ní se workflow
  hejguje jen na nová findings.
- **Fail-closed:** workflow nemá `continue-on-error: true`. Jakékoli finding v scope
  (před baseline) failuje PR. CodeQL action infrastrukturní selhání též failuje
  closed — degradace na "skip security scan" není bezpečná.
- **Secrets/PII:** workflow neexponuje secrets, ne loguje tokeny, ne loguje výsledky
  s PII. Výsledky jsou SARIF uploadnuty do GitHub security tab. Config a workflow jsou
  testovány na absence secret references v ne-komentářových řádcích.
- **Testy:** `tests/python/test_sast_workflow_contract.py` validuje strukturu
  workflow + config bez PyYAML dependency.

Pro detailní baseline policy viz `docs/adr/0007-codeql-sast-baseline.md` a
`docs/V1_RELEASE_GATE.md#codeql-sast-gate`.
