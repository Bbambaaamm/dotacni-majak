# Dotační maják

**Najde. Pohlídá. Dotáhne.**

Dotační maják je veřejně prospěšná open-source služba, která pomáhá občanům, obcím, spolkům, firmám a dalším organizacím najít vhodné české i evropské dotační příležitosti, ověřit jejich podmínky z oficiálních zdrojů, hlídat změny a připravit další kroky až k žádosti.

## Produktový slib

- **Najde** — nehledá jen přesná klíčová slova; rozumí širšímu významu záměru.
- **Pohlídá** — sleduje nové výzvy, změny, dokumenty a termíny.
- **Dotáhne** — ukáže způsobilost, finance, přílohy, checklist a další krok.

## Zásady

1. Oficiální zdroj je jediný zdroj pravdy.
2. UNKNOWN není FAIL.
3. Relevance není totéž co způsobilost.
4. AI není jediný rozhodovací mechanismus.
5. Každé důležité tvrzení má provenance.
6. Rozbitý parser nesmí „zrušit“ výzvy.
7. Core funguje bez placeného LLM a bez automatického přechodu na placené služby.
8. UX musí odpovědět: **Co mám udělat teď?**

## Cílový stack

- Web/PWA: React + TypeScript
- API: Cloudflare Workers
- Relational data: Cloudflare D1
- Raw snapshots: Cloudflare R2
- Semantic index: Cloudflare Vectorize
- Heavy ingestion: Python + GitHub Actions
- Search: FTS5 + ontologie + semantic retrieval + deterministic rules

## Struktura repozitáře

```
apps/
  web/
  api/
pipelines/
  ingestion/
  extraction/
  embeddings/
packages/
  canonical-schema/
  source-sdk/
  ontology/
  search/
  eligibility/
  finance/
  provenance/
  notifications/
  ui/
connectors/
data/
docs/
tests/
.github/
```

## Fáze

- **MVP:** skutečné hledání, provenance, první zdroje, eligibility, finance, Project Watch.
- **Beta:** širší pokrytí, workspace žádosti, porovnání, export, Web Push, změnová timeline.
- **v1.0:** produkční spolehlivost, široké pokrytí, security/privacy/accessibility gate, historická inteligence a spolupráce.

Podrobnosti: [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [DATA_MODEL.md](DATA_MODEL.md) · [SOURCE_ADAPTERS.md](SOURCE_ADAPTERS.md) · [INGESTION.md](INGESTION.md) · [BRAND.md](BRAND.md) · [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)

> Dotační maják není poskytovatelem dotace. Rozhodující jsou vždy oficiální podmínky příslušného poskytovatele.


## Lokální spuštění

Po `npm install` spouštějte projekt z kořene repository:

```bash
npm run dev
```

Tento příkaz:
1. aplikuje D1 migrace do lokální persistentní databáze,
2. pokud lokální NSA data chybí nebo jsou starší než 6 hodin, pokusí se je obnovit z oficiálního webu přes bezpečný Source Adapter,
3. uloží RAW snapshots do lokálního ignorovaného adresáře `.local/raw`,
4. naplní canonical D1 a FTS search index,
5. spustí API Worker na `http://127.0.0.1:8787`,
6. spustí web na `http://localhost:5173`,
7. Vite proxyuje `/api/*` do lokálního API.

> Samotné `npm --workspace @dotacni-majak/web run dev` spustí pouze frontend. Vyhledávání pak nemá backend.

### Lokální dotační data

Automatický start `npm run dev` obnovuje pouze **Národní sportovní agenturu**, aby běžný frontend restart nemusel procházet široký agregátor.

Pro širší lokální dataset spusťte:

```bash
npm run dev:data:refresh
```

Tento příkaz zpracuje odděleně:
- Národní sportovní agenturu,
- DotaceEU.cz.

Každý zdroj má vlastní RAW snapshots a vlastní D1 import transakci. Selhání jednoho zdroje nemaže ani nepřepisuje last-known-good data druhého.

Pouze NSA lze ručně obnovit:

```bash
npm run dev:data:refresh:nsa
```

Refresh si vytvoří lokální Python `.venv`, nainstaluje pouze potřebné open-source dependency pro Source SDK a příslušné connectory, stáhne veřejná oficiální data přes GuardedHttpClient a idempotentně je publikuje do lokální D1.

Pokud je oficiální zdroj dočasně nedostupný, `npm run dev` se přesto spustí a web ukáže poslední dostupná nebo prázdná data. Výpadek zdroje nevytváří falešné výzvy.

Pro vývoj bez automatického refreshu lze nastavit `DEV_SKIP_AUTO_REFRESH=1`.

QA/demo stavy výsledkové stránky jsou povoleny pouze explicitním parametrem `demoState`; běžný uživatelský search je nikdy nepoužívá.
