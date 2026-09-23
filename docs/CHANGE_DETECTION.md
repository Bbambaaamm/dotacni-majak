# Change Detection

Change detection porovnává dvě immutable `GrantCallVersion` reprezentace a vytváří konkrétní `ChangeEvent`.

## Zásada
Neupozorňujeme jen „dokument se změnil“.

Pokud canonical data dovolí určit konkrétní rozdíl, event obsahuje:
- field_path,
- old_value,
- new_value,
- change_type,
- severity,
- evidence_id.

## Deterministická klasifikace

### CRITICAL
- submission deadline,
- applicant eligibility rules,
- support rate / grant limits / payment rules,
- project budget limits,
- OPEN → PAUSED/CLOSED/CANCELLED.

### IMPORTANT
- supported activities,
- requirements/přílohy,
- běžná status změna, která výzvu nezavírá.

### INFORMATIONAL
- document hash/version change bez ještě známého strukturálního dopadu.

### EDITORIAL
- title/summary text bez změny známých podmínek.

## Evidence
ChangeEvent preferuje evidence nové verze pro konkrétní field_path; pokud není, použije evidence staré verze.

## Idempotence
ID eventu je deterministické z:
`grant_call_id + from_version_id + to_version_id + change_type + field_path`.

Stejný diff tedy nevytvoří dva logicky různé eventy.

## Další fáze
Document semantic diff může později zvýšit DOCUMENT_CHANGED na konkrétní strukturální event, ale generativní AI sama nikdy neurčuje závaznou dotační podmínku.
