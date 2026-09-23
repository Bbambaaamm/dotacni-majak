# Application Workspace

Workspace je hlavní část slibu **Dotáhne**.

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
