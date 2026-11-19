# Application Workspace

Workspace je hlavní část slibu **Dotáhne**.

## Bounded Dotáhne flow (#511)

Z detailu výzvy vede „Chci tuto dotaci“ přes založení anonymního projektu k
`POST /projects/:projectId/workspaces` (`{grantCallId}`); existující projekt
nabídne explicitní založení. Všechny `GET /projects/:projectId/workspaces`,
`GET /projects/:projectId/workspaces/:workspaceId` a
`PATCH /projects/:projectId/workspaces/:workspaceId/tasks/:taskId`
vyžadují projektový owner bearer capability. Neautorizované a cizí projekty
vracejí 404, sdílený read-only odkaz workspace neobsahuje. Capability zůstává
jen v sessionStorage; po ztrátě není obnovitelná.

Unikátní `(project_id, grant_call_id)` zajišťuje idempotentní založení;
`baseline_grant_version_id` se nikdy nepřepisuje. První zápis workspace a
checklistu probíhá atomicky v D1 batch. Požadavky jsou převzaty z publikované
verze; podmíněný požadavek bez zjištěné podmínky zůstává BLOCKED. Protože tento
tok nemá vstupy pro deterministické eligibility/finance vyhodnocení ani jistotu
úplnosti normalizovaných požadavků, tyto tři neznámé kroky jsou nezměnitelné
blokery. Procento popisuje jen splnění kroků, nikoli šanci na podporu.

Při owner read se porovná výchozí a aktuální publikovaná verze. Přednost
mají uložené `change_events` vytvořené deterministickým ChangeDetector; pokud
consumer ještě neběžel, API konzervativně porovná jen známá pole verze a
nově zjištěné požadavky. Nepřítomnost požadavku v nové normalizaci není důkaz
jeho odstranění, původní úkoly zůstávají a je nutná kontrola plného znění.
Změny termínu, stavu a známých požadavků se ukáží s dostupným evidence ID a
odkazem na zdroj; bez strukturovaného rozdílu je výslovně nutná kontrola celého
znění. Při chybě obnovení UI skryje staré úkoly, zakáže jejich změny a nabídne
nové načtení.
Nová verze generuje per-workspace/per-version persistentní idempotentní
upozornění (`workspace_version_alerts`) a výzvu k review jako první Next Action.
Upozornění se vytváří při autorizovaném načtení workspace, nikoli asynchronní
push; bez návštěvy stránky není doručeno. RAW/hash selhání publisheru nesmí
změnit current pointer ani upozornění. Testovací publisher je pouze lokální
fixture, veřejný endpoint pro simulaci neexistuje.

Lokální reprodukce: v izolovaném worktree s instalovanými npm balíčky a
Playwright Chromium spusťte `npm run test`, `npm run api:test`,
`npm run web:test`, `npm run web:e2e` (poslední příkaz migruje a znovu naplní
pouze `.wrangler/e2e` a běží proti skutečnému lokálnímu Workeru/D1). Pro
Python testy musí `PYTHONPATH` ukazovat na `packages/*/src` a
`pipelines/ingestion/src` z právě testovaného worktree; staré editable venv
nenahrazuje tento explicitní import. Browser spec
`tests/e2e/workspace-flow.spec.ts` ověřuje vlastníka/cizí capability,
checklist, reload, immutable baseline, deterministické change_events z RAW-first
simulace, a11y, idempotentní upozornění, vadný RAW hash a bezpečné selhání UI.
Test navíc ověřuje `change_events.evidence_id → field_evidence → document_versions`
proti SHA-256 a URL uloženého RAW snapshotu (lokální simulace).
Není to důkaz produkčního plánovače, push doručování ani skutečné žádosti.

## Baseline
Workspace vždy ukládá `baseline_grant_version_id`.

Pokud current GrantCallVersion != baseline:
> Podmínky výzvy se od zahájení přípravy změnily.

Workspace se nesmí tvářit jako aktuální bez review.

## Task sources
- REQUIREMENT
- ELIGIBILITY
- FINANCE
- USER

## Necessity
- REQUIRED
- CONDITIONAL
- RECOMMENDED

CONDITIONAL s neznámou podmínkou je blocking, dokud se nerozhodne, zda se na projekt vztahuje.

## Readiness
Readiness je **dokončenost konkrétních kroků**, ne pravděpodobnost získání dotace.

Stavy:
- BLOCKED
- NEEDS_ACTION
- READY

`completion_percent` počítá DONE / active tasks. NOT_APPLICABLE se nepočítá.

RECOMMENDED task může zůstat otevřený a workspace přesto být READY_TO_SUBMIT; blocking tasks nikoliv.

## Co udělat teď
Engine vždy vybírá next action:
1. blocking task,
2. nižší priority,
3. dřívější due date,
4. stabilní ID.

Eligibility UNKNOWN a finance NEEDS_INFORMATION se převádějí na konkrétní blocking tasks.

## Dokumenty
Persistence model ukládá pouze metadata/storage_ref. Samotné bezpečné upload/storage řeší samostatná security/deployment vrstva.
# Kontroly integrity a mobilního zobrazení

Čtení pracovního prostoru odmítne neúspěšný nebo prázdný výsledek načtení
uložených úkolů jako `503 WORKSPACE_UNAVAILABLE`. Chybějící checklist není
příprava se 100% dokončením. Regresní testy používají skutečný SQLite s úplnými
migracemi a simulují ztrátu úkolů i neúspěšný D1 výsledek.

Prohlížečový tok se ověřuje také při šířce 390 px včetně axe. Mobilní navigace
a pracovní karty mají omezenou šířku, takže dlouhé identifikátory ani změny
verzí nerozšiřují celou stránku.
