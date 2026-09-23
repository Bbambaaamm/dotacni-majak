# Research prvních oficiálních zdrojů — 2026-09-23

Tento dokument zachycuje ověřený stav retrieval možností pro první prioritní zdroje Dotačního majáku.

## Zásada

Nevymýšlet API tam, kde oficiální zdroj veřejné API nedokumentuje.

Preferované pořadí:
official API → official open data → RSS/Atom → JSON/XML/CSV/XLSX → HTML → PDF/DOCX.

---

## 1. EU Funding & Tenders Portal

### Autorita
Oficiální portál Evropské komise.

### Ověřený retrieval mechanismus
**Public REST API.**

Oficiální dokumentace:
https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis

Dokumentace potvrzuje veřejné služby:
- Grants & Tenders
- Topic Details
- Grant Updates
- FAQ Index / Details
- Organisation Public Data
- Partner Search
- Project & Results

SEARCH API používá HTTPS POST proti:
https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***

FACET API:
https://api.tech.ec.europa.eu/search-api/prod/rest/facet?apiKey=SEDIA&text=***

### Adapter strategy
RetrievalMode.API / JSON.

Primární identity:
- topic identifier / call identifier dle API payloadu.

### Change monitoring
Používat Grant Updates service + normalizovaný diff topic detailu.

### Refresh
Začít konzervativně 6 h pro discovery a častěji jen v deadline-sensitive okně, po ověření skutečných limitů.

### Stav
READY_FOR_CONNECTOR.

---

## 2. DotaceEU

### Autorita
Oficiální portál fondů EU v ČR.

Výzvy:
https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy

Harmonogramy:
https://www.dotaceeu.cz/cs/jak-ziskat-dotaci/vyzvy/harmonogramy-vyzev

### Ověřený retrieval mechanismus
Veřejný HTML katalog výzev.

Stránka aktuálně zveřejňuje:
- otevřené výzvy,
- status,
- program,
- termín podání,
- filtrování,
- zobrazení dalších výsledků.

Stránka nabízí také stažení kalendáře ve formátu XLSX.

Harmonogramy jsou zveřejněné jako samostatné oficiální dokumenty.

### Co zatím NENÍ ověřeno
Veřejné oficiální REST API nebylo v research nalezeno.

### Adapter strategy
1. Preferovat oficiální XLSX/export tam, kde pokrývá potřebná pole.
2. Pro katalog/detail použít HTML connector.
3. Dokumenty/harmonogramy ingestovat jako oficiální artefakty.
4. Před implementací zjistit skutečný pagination/load-more endpoint v browser network traffic pouze jako veřejně dostupné rozhraní; neobcházet ochrany.

### Stav
READY_FOR_CONNECTOR_RESEARCH_FIXTURE.

---

## 3. Národní sportovní agentura

### Autorita
Národní sportovní agentura.

Investiční výzvy:
https://nsa.gov.cz/dotace-investicni/

Příklad detailu:
https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/

### Ověřený retrieval mechanismus
Veřejné HTML listing/detail stránky + přílohy/dokumenty.

Detail výzvy obsahuje mimo jiné:
- datum vyhlášení,
- zahájení příjmu,
- ukončení příjmu,
- alokaci,
- typ výzvy,
- popis podporované oblasti,
- odkazy/přílohy.

### Identita
Preferovat oficiální číslo výzvy, např. `16/2026`, jako source external identity spolu s provider namespace.

### Adapter strategy
RetrievalMode.HTML + PDF/DOCX/XLSX podle příloh.

### Change monitoring
Hash detail HTML + jednotlivých příloh.
Změna dokumentu vytváří DocumentVersion, nikoli přepis.

### Stav
READY_FOR_CONNECTOR.

---

## 4. Jednotný dotační portál MF / RISPF

### Autorita
Ministerstvo financí / Státní pokladna.

Oficiální informace:
https://statnipokladna.gov.cz/cs/rozpocet/programove-financovani/jednotny-dotacni-portal-jdp/zakladni-informace

### Ověřený stav
Oficiální stránka potvrzuje webový portál RISPF/JDP pro digitalizaci národních dotačních výzev.

### Co zatím NENÍ ověřeno
Veřejné oficiální API pro systematické čtení katalogu výzev nebylo v research nalezeno.

### Adapter strategy
NESPĚCHAT s implementací API adapteru.

Další research musí zjistit:
- veřejnou URL katalogu výzev,
- stabilní identitu výzvy,
- případný export/open-data endpoint,
- zda je listing dostupný bez přihlášení,
- podmínky a dokumenty.

Pokud není bezpečný veřejný strojový katalog, connector se odloží a JDP bude pokryt přes konkrétní poskytovatele, dokud se nenajde oficiální cesta.

### Stav
RESEARCH_REQUIRED.

---

## 5. SFŽP

### Autorita
Státní fond životního prostředí ČR.

Oficiální web:
https://www.sfzp.cz/

Příklad oficiálního dokumentu výzvy:
https://www.sfzp.cz/files/documents/storage/2025/10/10/1760086659_V%C3%BDzva_NP%C5%BDP_26_2025_Recyklace%20textilu.pdf

### Ověřený retrieval mechanismus
Veřejný web + oficiální PDF dokumenty výzev.

### Co zatím NENÍ ověřeno
Jednotné veřejné REST API/open-data rozhraní pro všechny výzvy nebylo v research nalezeno.

### Adapter strategy
- nejprve zjistit stabilní veřejné listing pages jednotlivých programů,
- HTML discovery,
- PDF jako authoritative call document,
- oddělit jednotlivé programy (OPŽP, NPŽP, Modernizační fond, případně další) v canonical Programme modelu,
- neplést finanční nástroje a granty.

### Stav
READY_FOR_DEEPER_SOURCE_MAPPING.

---

# Doporučené pořadí prvních connectorů

1. **EU Funding & Tenders** — nejčistší oficiální API.
2. **NSA** — jednoduchý a důležitý HTML/PDF connector; zároveň výborný golden scenario pro tenisovou infrastrukturu.
3. **DotaceEU** — klíčový široký CZ katalog, ale nejprve zafixovat paging/export strategii.
4. **SFŽP** — rozdělit podle programových listingů.
5. **JDP** — pokračovat až po ověření veřejné retrieval cesty.

# MVP závěr

První produkční connector doporučený k implementaci:
**EU Funding & Tenders (#13)**.

První český connector doporučený paralelně:
**NSA (#16)**.

Tato volba dává rychle:
- jedno robustní API,
- jeden český HTML/PDF source,
- možnost ověřit celý Source Adapter Contract na dvou výrazně odlišných typech zdrojů.
