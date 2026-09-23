# První zdroje — retrieval research

Stav ověření: **2026-09-23**

Tento dokument zachycuje pouze ověřené veřejné integrační cesty. Kde oficiální API není doložené, nesmíme si jej domýšlet.

## 1. EU Funding & Tenders Portal

### Autorita
European Commission — Funding & Tenders Portal.

### Ověřená integrační cesta
Oficiální veřejné REST API:

- API dokumentace: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis
- SEARCH endpoint: https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***
- FACET endpoint: https://api.tech.ec.europa.eu/search-api/prod/rest/facet?apiKey=SEDIA&text=***

SEARCH API používá HTTPS **POST**. Filtrovací query je JSON v multipart/form-data. Dokumentace uvádí mimo jiné:
- Grants & Tenders service,
- Topic Details service,
- Grant Updates service,
- Project & Results.

Pro grant search dokumentace používá typy 1/2/8 podle konkrétního dotazu a status reference codes 31094501/31094502/31094503. Přesné typové mapování pro náš grant-only scope musí mít contract fixture a live smoke test — nespoléhat na domněnku.

### Identity
Primární kandidát: topic/call `identifier` z API. Canonical identity musí zachovat i source external id/reference.

### Status
Mapovat pouze z oficiálních status codes přes explicitní tabulku/facet resolution.

### Documents/details
Topic Details service a lidská Topic page. Grant Updates použít pro monitoring změn.

### Refresh
MVP návrh: každé 4 h; při blížícím se deadline lze snížit interval po budget checku.

### Poznámka
Náš současný GuardedHttpClient podporuje GET/HEAD; před connector implementací je nutné přidat bezpečný read-only POST/multipart režim.

---

## 2. DotaceEU

### Autorita
Ministerstvo pro místní rozvoj / DotaceEU.

### Ověřené veřejné zdroje
- Výzvy: https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy
- Harmonogramy: https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy/harmonogramy-vyzev

Veřejná stránka Výzvy obsahuje:
- dotační tituly,
- finanční nástroje,
- unijní programy,
- stav,
- programové období,
- termín pro podání,
- filtry a další stránky/záznamy.

Stránka nabízí také **XLSX kalendář**; používat jej jako doplňkový/cross-check zdroj, ne jako náhradu detailu výzvy.

### Retrieval
HTML discovery + detail/document links. Neexistující API nesmí být předpokládáno.

### Identity
Použít stabilní detail URL / oficiální kód výzvy, pokud je v detailu dostupný. Při nejasnosti vytvořit POSSIBLE_DUPLICATE místo agresivního merge.

### Status
Mapovat lidské stavy (např. Otevřená/Plánovaná/pozastavená) explicitně a uchovat native status.

### Refresh
MVP: každé 4 h. Harmonogram 1× denně nebo při změně dokumentu.

---

## 3. Jednotný dotační portál (JDP / JDP2)

### Autorita
Ministerstvo financí / RISPF.

### Ověřený stav
Oficiální informace MF/Státní pokladny potvrzují, že JDP je webový portál pro národní dotační výzvy zapojených resortů. V roce 2026 probíhá přechod na **JDP2**; oficiální resortní informace uvádějí nový portál:
https://jdp2.mf.gov.cz/

Historická/veřejně indexovaná instance:
https://jdp.mf.gov.cz/rispf/

### Retrieval
**Nesmíme zatím hardcodovat starý JDP endpoint jako current source.**

Před produkčním connector:
1. live contract test JDP2 public landing/list,
2. zjistit, zda discovery funguje server-rendered HTML, JSON/XHR nebo jiným veřejným rozhraním,
3. nepoužívat autentizované žadatelské části,
4. neobcházet JS/auth ochrany.

Pokud JDP2 veřejný discovery endpoint nebude stabilní, použít oficiální stránky poskytovatelů jako source-of-truth a JDP jen jako podací/secondary reference.

### Refresh
Po potvrzení retrieval metody. Výchozí návrh 4–6 h.

---

## 4. Národní sportovní agentura

### Autorita
Národní sportovní agentura.

### Ověřené veřejné zdroje
- investiční výzvy: https://nsa.gov.cz/dotace-investicni/
- neinvestiční výzvy: https://nsa.gov.cz/dotace-neinvesticni/
- parasport: https://nsa.gov.cz/dotace-neinvesticni-parasport/

Detail výzvy má veřejně dostupné např.:
- datum vyhlášení,
- začátek/konec příjmu,
- alokaci,
- typ výzvy,
- textový popis,
- dokumenty/odkazy.

Referenční fixture pro golden sport scenario:
https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/

### Retrieval
HTML listing → detail → dokumenty (PDF/ostatní veřejné přílohy).

### Identity
Oficiální číslo výzvy + rok (např. 16/2026), doplněné source URL.

### Status
Listing rozlišuje otevřené/ukončené sekce. Canonical status se nesmí měnit pouze proto, že záznam zmizel z listingu.

### Refresh
2–4 h v období častých změn, jinak 6 h.

---

## 5. OPŽP / SFŽP

Tuto oblast je vhodné rozdělit minimálně na dva Source Adaptery.

### 5A. Operační program Životní prostředí 2021–2027

Ověřené zdroje:
- nabídka dotací: https://2021-2027.opzp.cz/nabidka-dotaci/
- detail výzev: např. https://opzp.cz/dotace/108-vyzva/

Veřejné detaily obsahují:
- stav,
- typ,
- termín,
- alokaci,
- popis,
- dokumenty,
- příjemce podpory.

Retrieval: HTML listing/detail + veřejné dokumenty.

Identity: číslo výzvy + programové období / detail URL.

### 5B. Modernizační fond / SFŽP

Veřejné detail pages existují na sfzp.cz, např.:
https://www.sfzp.cz/dotace-a-pujcky/modernizacni-fond/vyzvy/detail-vyzvy/?id=27

Detail může obsahovat:
- termíny,
- alokaci,
- podporované aktivity,
- kdo může žádat,
- výši podpory,
- dokumenty.

Retrieval: HTML listing/detail + documents. Implementovat jako samostatný adapter od OPŽP kvůli odlišnému webu a doménovému modelu.

---

## Priority pro MVP

1. **EU Funding & Tenders** — nejlepší strojově čitelný oficiální API zdroj.
2. **NSA** — jednoduchý HTML → detail → documents model a zároveň golden sport scenario.
3. **OPŽP** — bohatý strukturovaný detail + dokumenty.
4. **DotaceEU** — široké pokrytí a harmonogramy.
5. **JDP2** — až po live ověření současné veřejné retrieval cesty.

## Cross-source pravidlo
Stejnou výzvu z více oficiálních zdrojů neslučovat agresivně. Nejprve exact official identifier/code, potom deterministic match, jinak POSSIBLE_DUPLICATE k review.
