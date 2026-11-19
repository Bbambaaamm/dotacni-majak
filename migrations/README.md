# D1 / SQLite migrations

Migrace jsou aplikovány v lexikografickém pořadí a nesmí být po merge přepisovány. Každá změna schématu dostane novou migration.

## Finanční reprezentace
Peníze se v databázi ukládají jako **integer minor units** (např. haléře/centy), nikoliv floating point.

Příklad:
- 4 000 000,00 Kč → `400000000` minor units.

Procenta podpory/spoluúčasti se ukládají jako **basis points**:
- 90 % → `9000`
- 12,5 % → `1250`

Tím se vyhneme chybám binárního floating pointu v kritických finančních výpočtech.

## Timestampy
Časy jsou ISO-8601 text v UTC, pokud konkrétní doména nevyžaduje explicitní timezone.

## Testování
`tests/python/test_migrations.py` aplikuje všechny migrations do in-memory SQLite s aktivními foreign keys a kontroluje kritické tabulky/indexy/constraints.


## Geography and applicant normalization

Migration `0023_geography_applicant_rules.sql` adds:
- hierarchical geographies with NUTS/LAU/ORP/MAS identifiers,
- INCLUDE/EXCLUDE grant applicability rules,
- normalized applicant type hierarchy,
- optional normalized applicant type/geography references on profiles,
- explicit value type + provenance/verification fields on dynamic applicant attributes.

The legacy `applicant_profiles.applicant_type` enum remains in canonical v1 for
runtime compatibility. `applicant_type_id` is additive and nullable until seed
data/mapping (#227) is available.

Dynamic attribute migration preserves existing rows. Invalid legacy JSON is
quoted rather than discarded; such values remain reviewable instead of causing
silent data loss.

## Applicant profile ownership (0029)

`0029_applicant_profile_owner_identity.sql` makes `user_id` unique for non-null
owners and changes the IČO index to non-unique. Existing profile rows and their
IDs are preserved. Legacy token-hash keys are mapped to `projects.owner_user_id`
when a live capability still links them to a project. Null keys and keys whose
token was already rotated or revoked remain unchanged for manual reconciliation.
If two existing rows have the same non-null `user_id`, the unique-index statement
fails. If two legacy records map to one owner, the update fails atomically.
Inspect and reconcile those records manually before retrying; do not choose one
arbitrarily, since both may hold applicant data.
