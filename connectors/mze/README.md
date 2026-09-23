# MZe / SZIF connector

Oficiální Source Adapter pro veřejně dostupné dotační výzvy Ministerstva zemědělství a veřejné dokumenty SZIF odkazované z oficiálních stránek.

## Discovery

Primární veřejný index:
- https://mze.gov.cz/public/portal/mze/vyhledavani/narodni-dotace

Strategický plán SZP je evidován jako důležitý rozcestník/harmonogram:
- https://mze.gov.cz/public/portal/mze/dotace/szp-pro-obdobi-2021-2027/harmonogram-vyzev

Connector publikuje konzervativně pouze stránky identifikované jako konkrétní výzvy. Výsledkové seznamy, zpřesnění zásad, obecné metodiky, formuláře a aktuality nejsou samostatný GrantCall.

## SZIF omezení

Přímý veřejný index SZIF `https://szif.gov.cz/cs/narodni-dotace` je v září 2026 chráněn CAPTCHA. Connector tuto ochranu **neobchází**.

Dokumenty hostované na `szif.gov.cz` / `szif.cz` lze stáhnout pouze tehdy, pokud na ně vede veřejný oficiální odkaz z připojeného zdroje.

Toto omezení musí být viditelné v Source Coverage; absence přímého SZIF discovery neznamená, že program neexistuje.

## Extrakce

Kde je údaj přímo na detailu výzvy, connector získává:
- název,
- otevření/uzavření příjmu žádostí,
- stav OPEN/PLANNED/CLOSED,
- rok/kód výzvy, pokud je zjistitelný,
- oprávněné žadatele,
- podporované oblasti,
- způsob podání,
- PDF/DOC/DOCX/XLS/XLSX přílohy.

## Safety

- RAW-first,
- GuardedHttpClient,
- žádné CAPTCHA bypass,
- konzervativní discovery,
- fixtures + live smoke test,
- zmizení z indexu není CANCELLED.
