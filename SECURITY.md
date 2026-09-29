# Security Policy

Tento dokument popisuje, jak hlásit bezpečnostní chyby, jaký je triage a
response workflow, jak hodnotíme závažnost a jak se chováme při incidentu.
Podrobný threat model najdete v [`docs/SECURITY.md`](docs/SECURITY.md),
provozní runbook v [`docs/RUNBOOK.md`](docs/RUNBOOK.md) a v1.0 security gate
v [`docs/V1_RELEASE_GATE.md`](docs/V1_RELEASE_GATE.md).

## Podporované verze

`Dotační maják` je open-source projekt před v1.0. Podporujeme:

| Verze    | Podpora      | Poznámka                                                   |
| -------- | ------------ | ---------------------------------------------------------- |
| `main`   | Aktivní      | Vývojová verze; může obsahovat nestabilní změny.           |
| Poslední veřejný deployment | Omezený | Opravy kritických zranitelností jsou backportovány sem.    |
| Starší release | Ne    | Není podporováno; upgrade na aktuální `main` je požadován. |

Před v1.0 nejsou zaručeny ani backwards-compatible změny. CVE nebo security fix
neuhlásíme pro verze podporované jen "best-effort".

## Sledování / severity

Používáme třídění podle dopadu, konzistentní s `docs/RUNBOOK.md`:

- **SEV-1 (kritický)** — únik nebo změna citlivých údajů, nesprávná
  autorizace, raw kapabilita/share token ve veřejném logu, nezabezpečený SSRF
  path, veřejný citlivý applicant/project payload, automatický placený upgrade
  bez potvrzení, nekontrolovaný file parsing. Okamžitý response.
- **SEV-2 (vážný)** — hlavní API/search/workspace nefunguje, zdrojové pokrytí
  významně omezené, ale integrita posledních ověřených dat zůstává, nebo
  nedostatečné log-redaction / auditní díra. Do 72 hodin.
- **SEV-3 (střední)** — dílčí zdroj/funkce omezená, existuje bezpečný fallback,
  nebo nekritický dokumentační/artefactní gap. Do 7 kalendářních dnů.

Priority je **integrita a bezpečnost, ne dostupnost za každou cenu**. Viz
`docs/SECURITY.md` → *Incident principle*.

## Nahlášení zranitelnosti (private contact)

**Nehlaste bezpečnostní chyby do veřejného issue**, pokud by veřejné zveřejnění
mohlo usnadnit zneužití (viz také `CONTRIBUTING.md`).

### Primární kanál — GitHub Security Advisories

Projekt používá GitHub **Private vulnerability reporting** (tlačítko
*Report a vulnerability*). Tento kanál je preferovaný, protože:

- je šifrovaný a dostupný jen týmu repozitáře,
- umožňuje koordinované (embargované) zveřejnění,
- podporuje CVE a automatické review před merge.

> **Maintainer action (repo setting, ne v kódu):** ve `Settings → Security &
> analysis` zapnout *Private vulnerability reporting*. Dokud není zapnuté,
> tlačítko nebude viditelné. Toto není kódová změna — je nutné ručně povolit.

### Sekundární kanál (fallback)

Dočasně, dokud není nastaven dedikovaný security contact, můžete otevřít
**privátní GitHub issue** s label `security` a obsahovat "[SECURITY]" v názvu.
Tento kanál **není šifrovaný ani embargovaný** a nesmí obsahovat exploit kód
ve formě, která by mohla být veřejně viditelná — ponechte jen popis a
kroky k reprodukci v textu. Pro citlivé detaily použijte
**primární kanál** (Security Advisories).

**Nespoléhejte se na e-mailové adresy uvedené v git logech ani commits ani
nikdy nepublikujte reprodukční kód pro SEV-1 veřejně dříve než dojde ke fixu.**

### Co v nálezku uvést

1. Popis zranitelnosti a dopad (proč je to security issue).
2. Verze/commit, kde se objevuje (`main` + SHA).
3. Vhodné kroky k reprodukci (bez veřejného exploitu).
4. Návrh opravy nebo vhodné reference (volitelné, ale vítáno).

### Co v nálezde **neuvádějte**

- žádný exploit kód veřejně před koordinovaným vydáním,
- žádné hot-kernel/root payloady ani DoS skripty,
- žádné ústné tokeny, heslovalky ani simulované credentials — použijte
  fixture/testovací hodnoty (viz `tests/python/test_document_security.py`).

## Triážní workflow

1. **Acknowledgement (≤ 72 h)** — tým potvrdí přijmutí nálezku a požádá o
   doplňující detaily, pokud jsou potřeba.
2. **Triage & severity** — určení SEV-1/2/3 a zodpovědného maintainera.
3. **Reproduction** — reprodukce na fixture nebo lokálním prostředí.
4. **Fix development** — malý, reviewovatelný PR; žádný fix commit
   nesmí narazit `main` dříve, než projde CI + security/DOD kontrolou.
5. **Coordinated disclosure** — embargo do doby vydání (viz níže).
6. **Release & verification** — fix je součástí release; security testy musí
   jet i na `main` i na releasovém artefaktu.
7. **Public disclosure** — až po ověření, že majoritní uživatelé mohou
   upgradovat; vydá se GHSA advisory + (pokud je CVE) CVE ID.

## Embargo a koordinované zveřejnění

- **Výchozí model:** coordinated disclosure (embargo) do doby, než je fix k
  dispozici a majoritní uživatelé mohou upgradovat.
- **Maximální lhůť pro embargo:** 90 kalendářních dnů od potvrzení. Pokud
  není fix k dispozici do 90 dnů, rozhodne tým o partial public disclosure
  (bez detailu exploitu) a/nebo o bezpečném degraded stavu.
- **Urgentní (SEV-1):** výjimka z embargo maximálně 72 hodin, pokud je
  aktivní exploitace nebo masové zneužití — rozhoduje maintainer.
- **Credit:** nepublikujeme jména ani detaily reportera bez jeho explicitní
  dovolení. Volitní reporteri mohou být uznáni v advisory (opt-in).

## Negative / abuse scénáře

Neshledáme jako security incident:

- běžné chyby dat nebo UX (hlásit jako běžné issue),
- "feature request" typu "přidejte validaci X" (bez konkrétního exploitu),
- návrhy na zlepšení threat modelu bez proof-of-concept,
- reporty z automatických šcannerů bez manuální validace (povinná revalidace
  core týmem; strojové reporty bez kontextu jsou zamítány jako šum).

**Ochrana před zneužitím kanálu:**

- spamující nebo opakující se reporty bez nových faktů blokujeme,
- pokud někdo pošle report obsahující malware/honeytoken, neotevíráme ho jako
  běžný ticket — interně se označí jako potential phishing a ignoruje se
  dál (viz *Social engineering* níže),
- nikdo z týmu nikdy nepožaduje přístup ke vašim systémům, úložištím ani
  credentials — pokud někdo tvrdí, že od "maintainera" požadoval přístup,
  neoznačujte to jako security report, ale jako **social engineering** a
  ignorujte.

**Social engineering:** neposílejte reprodukční data na externí servery,
neinstalovujte software z reportu a neposkytujte SSH/anonymní přístup
nikomu. Všechny testy provádějte izolovaně (viz `docs/DOCUMENT_SECURITY.md`,
`docs/LOCAL_DEVELOPMENT.md`).

## Fail-closed a bezpečný degraded stav

- Při nejistotě preferujeme **nedostupnost nové informace před publikací
  potenciálně chybného nebo podvrženého dotačního údaje** (viz *Incident
  principle* v `docs/SECURITY.md`).
- `disappearance != cancellation` a `UNKNOWN != FAIL` — parser/source failure
  nesmí provést **destruktivní** změny kanonicalu (viz `docs/RUNBOOK.md` §2,
  §3 a `docs/SECURITY.md` → *Data poisoning*).
- Při DEGRADED source se ponechá `last-known-good` canonical data a
  blokuje se destructive reconciliation (viz `docs/RUNBOOK.md` §2).
- Bezpečný fallback pro search: při výpadku Vectorize použijeme FTS +
  ontology + structured filtry; canonical data a eligibility zůstávají
  funkční a nikdy neprezentujeme relevance jako eligibility
  (viz `docs/RUNBOOK.md` §7).
- Capability/share tokeny: neznámý, zrušený i expirovaný odkaz se
  navenek nerozlišuje — vrací `404 SHARE_NOT_FOUND` (nikoli leak existence
  projektu, viz ADR-0007). Raw token **nikdy** není ukládán ani logován;
  ukládá se jen jeho SHA-256 hash a lze revokovat/rotovat.

## Secrets & PII v logu

- `secret_scanning` (včetně push protection) je **zapnut** v repozitáři —
  commit s leaknutým secretem je blokován.
- `secret_scanning_validity_checks` a
  `secret_scanning_non_provider_patterns` **nejsou** zapnuté — to je
  **residual risk**; doporučuje se zapnout v `Settings → Security & analysis`.
- Auditní logy uchovávají **pouze metadata** (událost, actor, timestamp,
  record hash, outcome) — **nikdy** raw capability/share tokeny, heslá,
  applicant PII ani citlivý project payload (viz ADR-0007 §3, ADR-0007
  *Privacy / retention dopad*, `docs/RUNBOOK.md` §11).
- Log redaction: libovolný log obsahující citlivý substring musí být
  označen `redact=true` před psaním/keší; centralizovaný log
  agregát povinně filtruje podle known-secret tvaru (GitHub secret-scanning
  patterns).
- **Fail-closed:** pokud není jisté, zda je daný field citlivý, zvolí se
  `redact` — raději neúplná zpráva než únik PII.

## Runbook & dokumentace

- **`docs/RUNBOOK.md`** — incident response, SEV-1/2/3, recovery tabletop,
  security incident §11, rollback checklist.
- **`docs/SECURITY.md`** — threat model, trust boundaries, hlavní threats.
- **`docs/DOCUMENT_SECURITY.md`** — bezpečnost sandboxu parserů, limity,
  MIME/XXE/path-traversal kontroly.
- **`docs/PRIVACY.md`** — data classes, retention, forbidden defaults.
- **`docs/V1_RELEASE_GATE.md`** — v1.0 security gate + evidence workflow.
- **`docs/V1_KNOWN_LIMITATIONS_TEMPLATE.md`** — šablonu pro známá omezení.

## Release gate

Podle `docs/V1_RELEASE_GATE.md` nesmí být vydaná v1.0 s:

- známým kritickým IDOR,
- raw capability/share token loggingem,
- nezabezpečeným SSRF path,
- neomezeným file parsingem,
- automatickým placeným upgrade,
- veřejným citlivým project/applicant payloadem,
- nevyřešenou critical dependency vulnerability bez explicitního risk acceptance.

`v1.0 Release Gate` GitHub Action provádí evidence workflow: každé gate
rozhodnutí má datum, release SHA a odkaz na evidence; rozhodnutí je `GO/NO-GO`
pouze ručně — automatizace nevyvoří PASS jen z existence dokumentu.

## Známá omezení / residual risks

1. `dependabot_security_updates` **vypnut** — security fixy nejsou automaticky
   navrhovány. Doporučuje se zapnout v `Settings → Security & analysis`.
2. `secret_scanning_non_provider_patterns` a `validity_checks` **vypnuté**.
3. GitHub private vulnerability reporting (GHSA) **vyžaduje ruční povolení**
   v repo settings — dokud to maintainer neudělá, primární kanál nebude
   aktivní a použije se fallback (privátní issue, nešifrovaný).
4. Žádný dedikovaný security mailing list / ticketing systém — odpovědnost
   spočívá u maintainerů; pro incidenty nad v1.0 je naplánován vlastní
   security response tým (zatím OPEN, viz `docs/ISSUE_ROADMAP.md`).
5. Embargo až do maximálně 90 dnů může zpoždovat public opravy u malého týmu —
   mitigace: SEV-1 má 72h výjimku.
