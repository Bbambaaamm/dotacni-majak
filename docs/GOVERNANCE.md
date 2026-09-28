# Governance — Dotační maják

Tento dokument popisuje pravidla pro ochranu repozitáře, review proces a merge politics.

## Branch protection — main

Main větev musí být chráněna následujícími pravidly:

### Required status checks

Následující CI checks musí projít před merge do main:

| Check | Význam |
|---|---|
| `foundation` | Hlavní CI job: typecheck, testy, build, E2E, všechny connector instalace, validace schémat |
| `CodeQL` | Statická analýza bezpečnosti (GitHub) |
| `GitGuardian Security Checks` | Detekce vydražených tajemství |

Opcionálně (po nasazení lint toolchain z #504):
| Check | Význam |
|---|---|
| `Analyze (javascript-typescript)` | ESLint + TypeScript analýza |
| `Analyze (python)` | Ruff lint analýza |
| `npm-audit` | Audit npm závislostí |
| `python-audit` | Audit Python závislostí |

### Zákaz přímého pushu

Přímý push do main je zakázán. Všechny změny musí přijít přes PR s review.

### Require review from Code Owners

Při zapnutí je vyžadován review od vlastníka CODEOWNERS souboru pro změny v kritických cestách (viz `.github/CODEOWNERS`).

### Squash merging

Squash merge je povolen a doporučen. Každý PR by měl být squashován do jednoho commitu s výzvou k zavření issue.

## CODEOWNERS

Soubor `.github/CODEOWNERS` definuje, kdo musí reviewovat změny v specifických cestách.

### Kritické cesty

| Cesta | Důvod |
|---|---|
| `schemas/` | Canonical schema změny ovlivňují všechny connectory a aplikace |
| `migrations/` | Databázové migrace jsou irreversible |
| `.github/` | GitHub konfigurace (workflows, CODEOWNERS, templates) |
| `wrangler.jsonc` | Cloudflare/Wrangler konfigurace |
| `apps/` | Hlavní aplikace (API, web) |
| `connectors/` | Každý connector je samostatná integrace s externím zdrojem |
| `packages/` | Core balíčky (eligibility, finance, search, atd.) |
| `pipelines/` | Ingestní pipeline |
| `scripts/` | Dev, ingest a refresh skripty |
| `docs/` | Dokumentace a specifikace |

### Single-owner zàsady

Repozitář má jednoho vlastníka (`Bbambaaamm`). CODEOWNERS zajišťuje, že:
1. Všechny změny jsou reviewovány (i při single-owner modelu)
2. Kritické cesty jsou explicitně identifikovány
3. Při přidání týmu se konfigurace snadno rozšíří

## Merge politics

### PR requirements

- PR musí být propojen s issue
- PR musí mít zelenou CI (všechny required checks)
- PR musí mít alespoň jedno review (od CODEOWNER v případě zapnutého CODEOWNERS)
- PR musí splňovat acceptace criteria z issue

### Squash commit message

Squash commit message by měl:
1. Začínat s title issue (např. `M0: ... (#502)`)
2. Zavírat issue (`


## Error scenarios

### Přímý push do main (pokud by byl povolen)
- Při zapnuté branch protection je přímý push odmítnut
- Výjimka: repository owner může 해지ovat protection (jen s explicitní motivací)

### CI neprošel před merge
- Merge je blokován forced-required checks
- Než se spustí nový CI run, merged commit neišle
- Řešení: upravit PR, nepočítat "stale" CI runs

### Kodografické změny bez CODEOWNER review
- Při zapnuté "Require review from Code Owners" je merge blokován
- Seznámení: CODEOWNERS review je povinné pouze pro změny v určených cestách
- Výjimka: změnyOwner může ignorovat svůj vlastní CODEOWNERS (pouze owner)

## Audit evidence

Všechny protection změny v main jsou auditovány GitHub Logs:
- Kdo, kdy a jakou změnou protection byl upraven
- Kdo a kdy byl merge proveden
- Kdo reviewoval a schválil PR

Audit evidence je dostupná v:
- GitHub Settings → Branches → main → "View details" (protection history)
- GitHub Settings → Audit log (repo-level events)

## Doporučení pro budoucí tým

- Při přidání nových colaborátorů aktualizujte CODEOWNERS
- Nové required checks přidejte do CI a následně do branch protection
- Dokumentujte každou noii ochranu v tomto souboru
