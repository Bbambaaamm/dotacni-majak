# Cloudflare deployment foundation

Dotační maják používá **Wrangler v4** a `wrangler.jsonc`, které Cloudflare doporučuje pro nové Workers projekty.

## Bindings

API Worker očekává:

- `DB` — D1 canonical databáze,
- `RAW` — R2 bucket pro RAW snapshots,
- `SEARCH` — Vectorize index pro aktivní SearchProfile,
- `ENVIRONMENT` — local/staging/production,
- `RELEASE_SHA` — auditovatelný release identifikátor.

Repository obsahuje pouze **lokální placeholder bindings**. Produkční IDs/secrets se nesmí commitovat.

## Zero-cost bezpečnost

- Repository nikdy automaticky nevytváří placené zdroje.
- CI používá pouze `wrangler deploy --dry-run`.
- Skutečné vytvoření D1/R2/Vectorize je explicitní administrativní krok.
- Žádný workflow neprovádí `wrangler deploy` bez explicitně přidaných Cloudflare credentials.
- UsageBudgetManager (#39) je další povinná vrstva před production release.

## Provisioning — explicitně, ručně/řízeným release workflow

Před prvním deployem:

```bash
npx wrangler@4 d1 create dotacni-majak-prod
npx wrangler@4 r2 bucket create dotacni-majak-raw-prod
npx wrangler@4 vectorize create dotacni-majak-search-prod --dimensions=<MODEL_DIMENSIONS> --metric=cosine
```

Výstupy se promítnou do produkční konfigurace/secrets mimo repository.

## Migrations

D1 migrations musí být aplikovány explicitně před kódem, který je vyžaduje. Storage rollback není součástí Worker rollbacku.

## Deploy doporučený postup

1. CI + migrations compatibility.
2. `wrangler versions upload` pro vytvoření testovatelné verze.
3. Smoke test Version URL.
4. `wrangler versions deploy` nebo řízený deployment.
5. Zkontrolovat `/health` a `/ready`.

## Rollback

Worker lze vrátit pomocí:

```bash
npx wrangler@4 rollback <VERSION_ID> --message "rollback: <reason>"
```

Pozor: rollback Workeru **nevrací stav D1/R2/Vectorize**. Každá DB migration proto musí být navržena s kompatibilitou předchozí verze nebo samostatným recovery plánem.

## Credentials

Minimální práva se mají omezit pouze na konkrétní Worker/resources. Secrets se přidávají pomocí Cloudflare secret managementu a nikdy přes git.
