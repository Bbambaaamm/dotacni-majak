# Dotační maják — Lint / Format / Type-check toolchain

Tento dokument popisuje kvalitní řetězec pro oba jazyky (TypeScript + Python).

## Nástroje

### Python

| Úloha | Nástroj | Verze | Reprodukovatelnost |
|---|---|---|---|
| Lint | Ruff | 0.6.9 | `pip install ruff==0.6.9` nebo `uv tool install ruff==0.6.9` |
| Formátování | Ruff format | 0.6.9 | Stejný balíček jako lint |
| Typová kontrola | Python `compileall` | — | V CI: `python3 -m compileall ...` |

**Konfigurace:** `ruff.toml` (kořen repozitáře)

**Skripty (npm):**
```
npm run lint:py          # pip install ruff && ruff check .
npm run format:py        # python3 -m ruff format .
npm run format:py:check  # python3 -m ruff format --check .
```

**Instalace lokálně:**
```bash
uv pip install ruff==0.6.9
# nebo
pip install ruff==0.6.9
```

### TypeScript

| Úloha | Nástroj | Verze | Reprodukovatelnost |
|---|---|---|---|
| Lint | ESLint (flat config) | 9.1.0 | `npx eslint@9.1.0 .` nebo globální instalace |
| Formátování | Prettier | 3.3.3 | `npx prettier@3.3.3 --check .` |
| Typová kontrola | TypeScript `tsc` | 7.0.2 | `npm run web:typecheck`, `npm run api:typecheck` |

**Konfigurace:** `eslint.config.js` (kořen), `.prettierrc` (kořen)

**Skripty (npm):**
```
npm run lint          # eslint .
npm run lint:fix      # eslint . --fix
npm run format        # prettier --write .
npm run format:check  # prettier --check .
npm run web:typecheck # tsc -b --pretty false  (web)
npm run api:typecheck # tsc -p tsconfig.json --noEmit  (api)
```

**Instalace lokálně:**
```bash
npm install -D eslint@9.1.0 @eslint/js typescript-eslint@8.10.0 prettier@3.3.3 eslint-config-prettier
```

### Pre-commit hooks

```bash
pre-commit install
```

Konfigurace: `.pre-commit-config.yaml`

## CI

V `.github/workflows/ci.yml` jsou přidány kroky do jobu `foundation`:

1. `pip install ruff==0.6.9` — instalace Python nástrojů
2. `ruff check .` — lint Python
3. `ruff format --check .` — formátovací kontrola Python
4. `npm install -g eslint@9.1.0 @eslint/js typescript-eslint@8.10.0 prettier@3.3.3 eslint-config-prettier` — instalace TypeScript nástrojů
5. `npm run lint` — lint TypeScript
6. `npm run format:check` — formátovací kontrola TypeScript

## Security / privacy / a11y

- **Security:** ESLint `no-console: warn` ochrání před debug výpisy v produkci
- **Privacy:** Prettier a Ruff nevidí obsah souborů — pouze formátují
- **a11y:** TypeScript typová kontrola (`tsc`) zachytí typové chyby; ESLint `recommended` zahrnuje základní pravidla; a11y testy jsou pokryté Playwright a11y smoke testy (`npm run web:a11y`)
- **Ruff:** `B` (bugbear) pravidla zachytí potenciální bezpečnostní problémy (např. `assert` v produkčním kódu, mutable default arguments)

## Chybový scénář

Viz `tests/python/test_lint_error_scenario.py` — automatický test, který:
1. Vytvoří dočasný Python soubor s úmyslnou chybou (nepoužitý import)
2. Spustí `ruff check` na něm
3. Ověří, že ruff chybu ohlásí

V CI běží jako součást `tests/python` — pokud ruff není nainstalován, test se přeskočí.
