# Applicant Profile & official resolvers

## Principle
Profil rozlišuje:
- údaje potvrzené uživatelem,
- údaje rozřešené z oficiálních veřejných zdrojů,
- UNKNOWN.

Resolver nikdy pouze podle právní formy ARES automaticky netvrdí, že je subjekt například „sportovní klub“ nebo „neziskovka“. Takové mapování vyžaduje samostatné explicitní pravidlo/ověření.

## ARES
Oficiální veřejné REST API:
- base: `https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/`
- detail: `GET /ekonomicke-subjekty/{ico}`
- Swagger: `https://ares.gov.cz/swagger-ui/`

Resolver ukládá pouze minimální fakta potřebná pro dotační eligibility:
- IČO
- obchodní název
- právní forma
- obec/adresa
- CZ-NACE

Celou odpověď ARES pro uživatelský profil zbytečně nepersistujeme.

ARES 1. 9. 2026 oznámil zpětně nekompatibilní API 1.40 plánované na 30. 9. 2026. Proto parser toleruje více reprezentací základních polí a live contract smoke běží odděleně od PR CI.

## Population / ČSÚ
Autoritativní zdroj pro počet obyvatel:
ČSÚ DataStat, dataset `OBY02E` (počet obyvatel až na úroveň obcí).

DataStat poskytuje veřejné API pro ad-hoc výběry:
`POST /api/dotaz/v1/data/sady/{sadaKod}/vlastni`.

Core applicant package definuje `MunicipalityPopulationResolver`. Konkrétní DataStat import/cache bude implementován samostatně; profil uchovává vždy:
- population
- as_of date
- source_reference

Tím se starší populační údaj nikdy netváří jako aktuální bez data platnosti.

## API (CRUD + refresh timestamp)

### Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/applicant-profile` | Bearer owner capability | Returns the caller's profile (keyed by hashed token) or `404 { profile: null }` when none exists. UNKNOWN ≠ FAIL. |
| `PUT` | `/applicant-profile` | Bearer owner capability | Creates or updates (upsert) the caller's profile. Body size ≤ 16 KB. |
| `POST` | `/applicant-profile` | Bearer owner capability | Alias of `PUT` — same upsert semantics. |
| `DELETE` | `/applicant-profile` | Bearer owner capability | Deletes the profile. Idempotent (returns `200 { deleted: true }` even if no profile exists). |
| `GET` | `/applicant-profile/last-resolved` | Bearer owner capability | Read-only. Returns `{ lastResolvedAt: "ISO-8601" | null }` — the most recent `observedAt` across all per-field provenance entries. Exposes only the timestamp, never PII. |

### Authorization
- Bearer token = anonymous project owner capability (same capability used by `/projects/{id}/watch`).
- Server-side: `hashOwnerToken(token)` → SHA-256 of `dotacni-majak-project-owner-v1\0` + token → used as `user_id` in `applicant_profiles`.
- Raw token is never stored. Missing/invalid token returns `404 OWNER_CAPABILITY_INVALID` (non-disclosing).

### Error semantics
| Code | HTTP | Meaning |
|---|---|---|
| `OWNER_CAPABILITY_INVALID` | 404 | Token missing/malformed/incorrect |
| `INVALID_JSON` | 400 | Body is not valid JSON |
| `EMPTY_BODY` | 400 | Body is empty |
| `REQUEST_TOO_LARGE` | 413 | Body exceeds 16 KB |
| `INVALID_PROFILE_INPUT` | 400 | Top-level body is not an object |
| `INVALID_APPLICANT_TYPE` | 400 | `applicantType` missing or malformed |
| `INVALID_ICO` | 400 | IČO not exactly 8 digits |
| `INVALID_VAT_STATUS` | 400 | Not one of UNKNOWN/PAYER/NON_PAYER |
| `INVALID_CZNACE_CODE` / `DUPLICATE_CZNACE_CODE` | 400 | CZ-NACE array validation |
| `INVALID_FIELD_SOURCE` / `INVALID_SOURCE_KIND` / `INVALID_OBSERVED_AT` | 400 | Provenance field validation |
| `PROFILE_UNAVAILABLE` | 503 | DB error during read/write (no internal details, no PII) |

### Provenance & refresh timestamp
- `field_sources_json` column stores per-field provenance: `sourceKind` (USER/ARES/CZSO/OTHER_OFFICIAL/DERIVED), `sourceReference`, `observedAt`, `verifiedAt`, `verificationStatus`, `evidenceId`.
- `lastResolvedAt` = `max(observedAt)` across all field sources. `null` when no official-source facts exist → caller knows a resolver refresh is due.
- Future slice: `POST /applicant-profile/resolve` will trigger an async ARES/ČSÚ refresh background job.
