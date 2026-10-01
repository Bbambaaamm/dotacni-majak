# Lokální vývoj

Tento dokument popisuje, jak nový přispěvatel spustí Dotační maják na lokálním počítači bez tribal knowledge.

## Požadavky / runtime předpoklady

| Nástroj | Minimální verze | Proč |
|---|---|---|
| Node.js | 20 (doporučeno 24 — viz `.nvmrc`) | Web, API, Wrangler CLI |
| npm | 10+ | Balíčky a workspace skripty |
| Python 3 | 3.12 | Ingestion pipeline (`dev:data:refresh`) |

Validaci můžeš spustit kdykoli:

```bash
node scripts/prerequisites.mjs
```

Skript ověří Node.js, npm a python3 a vypíše OK/CHYBA pro každý.

## Instalace

```bash
npm install
```

Tento příkaz nainstaluje Node.js balíčky (včetně `wrangler` v `apps/api`) a připraví TypeScript/Python workspace.

## Jednoduchý start

```bash
npm run dev
```

Tento příkaz (`scripts/dev.mjs`) provede kroky:

1. **DB migrace** — `npm run dev:db:migrate` aplikuje SQLite/D1 migrace lokálně.
2. **Data refresh** — pokud `.local/data-refresh.json` chybí nebo je starší než 6 hodin, automaticky stáhne oficiální data přes Source Adaptery.
3. **RAW snapshots** — ukládá surová data do `.local/raw` (git-ignored).
4. **Canonical naplnění** — naplní D1 canonical tabulky a FTS index.
5. **Spuštění API** — `app/api` na `http://127.0.0.1:8787`.
6. **Spuštění webu** — `app/web` na `http://localhost:5173`.
7. **Proxy** — Vite proxyjuje `/api/*` na lokální API.

> Samotné `npm --workspace @dotacni-majak/web run dev` spustí jen frontend. Bez backendu hledání nebude fungovat.

## Data refresh

Data se obnovují automaticky při `npm run dev`. Manuálně:

```bash
npm run dev:data:refresh
```

Pouze Národní sportovní agenturu:

```bash
npm run dev:data:refresh:nsa
```

Bez automatického refreshu: `DEV_SKIP_AUTO_REFRESH=1`.

## Testy

```bash
npm test
```

Spustí: `scripts/validate_schemas.py` + Python unit testy.

## Troubleshooting

### `python3: command not found`

Python 3 je potřebný pro ingestion. Nainstaluj [Python 3.12+](https://www.python.org/downloads/) a ujisti se, že `python3` je na PATH.

### `wrangler: command not found` nebo `node_modules/.bin/wrangler` chybí

```bash
npm install
```

### Port 8787 (API) nebo 5173 (web) je obsazen

```bash
lsof -i :8787    # najdi proces
kill -9 <PID>    # ukonči jej
```

Nebo použij jiný port: `npm --workspace @dotacni-majak/api run dev -- --port 8790`.

### D1 migrace selžou

Skript `dev` spustí `npm run dev:db:migrate` automaticky. Pokud selže:

```bash
npm run dev:db:migrate
```

Ujisti se, že Wrangler je nainstalovaný (`npm install`).

### Data refresh selže pro jeden zdroj

Každý zdroj má izolovaný refresh. Selhání jednoho neovlivní ostatní. Poslední úspěšná data zůstanou v `.local/`.

## Security / privacy

- **Credentials**: lokální dev Nikdy nepoužívá produkční API klíče ani úložiště. Vše běží lokálně přes `--local`.
- **RAW snapshots**: `python3 -m venv .venv` se vytvoří v kořeni repo. `.local/` je git-ignored.
- **Live endpoints**: `npm run dev` stahuje pouze veřejná oficiální data.
- **demoState**: QA stavy jsou povoleny jen explicitním `demoState` parametrem.
- **a11y**: E2E testy zahrnují a11y smoke (`npm run web:a11y`). Viz `docs/ACCESSIBILITY.md`.

## Shrnutí příkazů

| Co | Příkaz |
|---|---|
| Zkontrolovat předpoklady | `node scripts/prerequisites.mjs` |
| Nainstalovat závislosti | `npm install` |
| Spustit vývoj | `npm run dev` |
| Aplikovat DB migrace | `npm run dev:db:migrate` |
| Obnovit data | `npm run dev:data:refresh` |
| Spustit testy | `npm test` |
