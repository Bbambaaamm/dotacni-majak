# Sources


## Ministerstvo zemědělství / SZIF

- Discovery: veřejný index Národní dotace MZe
  - https://mze.gov.cz/public/portal/mze/vyhledavani/narodni-dotace
- Důležitý plánovací zdroj: harmonogram Strategického plánu SZP 2023–2027
  - https://mze.gov.cz/public/portal/mze/dotace/szp-pro-obdobi-2021-2027/harmonogram-vyzev
- Oficiální dokumenty mohou být hostované také na `szif.gov.cz` / `szif.cz`.
- Přímý index `https://szif.gov.cz/cs/narodni-dotace` je v září 2026 CAPTCHA-protected; Dotační maják ochranu neobchází.
- Coverage proto transparentně rozlišuje MZe-discovered calls od přímého SZIF discovery, které je aktuálně nepodporované.


## Technologická agentura ČR (TA ČR)

- Discovery: veřejná sekce **Aktuální možnosti podpory** na https://tacr.gov.cz/
- Konkrétní calls: oficiální stránky `/soutez/`
- Detail poskytuje alokaci, maximální podporu, intenzitu, uchazeče a lhůtu.
- Pokud detail uvádí přesné časy soutěžní lhůty, jsou preferovány před souhrnným datem.
- SISTA je pouze aplikační systém a connector jej nescrapuje.
- První coverage zahrnuje OPEN možnosti; PLANNED soutěže z harmonogramu budou mapovány samostatně.


## Dům zahraniční spolupráce (DZS)

- Erasmus+ Výzva 2026: https://www.dzs.cz/en/node/3607
- Evropský sbor solidarity — Projekty a granty: https://www.dzs.cz/program/evropsky-sbor-solidarity/projekty-granty
- Connector rozděluje veřejně publikované termíny na jednotlivé grantové akce a sektory.
- Jedna zdrojová stránka se během discovery ukládá do jednoho RAW snapshotu; jednotlivé records snapshot znovu používají.
- Centralizované aktivity spravované přímo Evropskou komisí nejsou duplikovány a patří do EU Funding & Tenders coverage.


## Národní rozvojová banka (NRB)

- Úvěry: https://www.nrb.cz/podnikatele/uvery/
- Záruky: https://www.nrb.cz/podnikatele/zaruky/
- Produkty jsou klasifikovány jako `LOAN`, `GUARANTEE` nebo `MIXED`; nejsou automaticky vydávány za dotace.
- Status `PAUSED` je zachován jako samostatný stav.
- Connector extrahuje veřejné parametry úvěru/záruky, příspěvkovou složku a oficiální dokumenty.
- WebKlient ani e-podatelna se nescrapují.


## MF ReD — historické podpory

- **Účel:** pouze historické příklady podpořených projektů; nikdy aktivní výzvy.
- **Autorita:** Ministerstvo financí / Registr dotací (IS ReD).
- **Oficiální dokumentace:** https://data.mf.gov.cz/topics/dotace
- **Formát:** komprimované CSV distribuce pro Dotace, Příjemce pomoci a Rozhodnutí.
- **Aktualizace:** Dotace jsou v katalogu označeny jako čtvrtletní.
- **Connector:** `connectors/red-history`.
- **RAW-first:** ano; každý ze tří exportů se ukládá samostatně.
- **Safety:** návratná finanční pomoc není zobrazena jako historický grant.
- **Live smoke:** `scripts/smoke_red_history.py`.


## Hlavní město Praha — regionální dotace

- **Oficiální zdroj:** Elektronická úřední deska MHMP, kategorie Granty.
- **Discovery:** veřejný RSS feed úřední desky s `kategorie_id=24`.
- **Detail:** oficiální notice-board detail na pražských doménách.
- **Connector:** `connectors/praha`.
- **RAW-first:** ano; RSS i detail se snapshotují.
- **Safety:** administrativní záznamy v kategorii Granty jsou konzervativně filtrovány; datum sejmutí z úřední desky se nikdy nepovažuje za deadline žádosti.
- **Live smoke:** `scripts/smoke_praha_connector.py`.
- **Coverage caveat:** RSS může obsahovat jen poslední část záznamů; tento connector je primárně monitoring nových/aktuálních grantových oznámení, ne kompletní historický archiv.


## Plzeňský kraj — eDotace

- **Oficiální zdroj:** https://dotace.plzensky-kraj.cz/verejnost
- **Discovery:** server-rendered veřejný index otevřených a připravovaných dotačních titulů.
- **Stable source identity:** číselné ID z URL `/verejnost/dotacnititul/{id}/`.
- **Detail:** účel, důvod, potenciální žadatelé, explicitní termíny, finance, administrátoři a přílohy.
- **Connector:** `connectors/plzensky`.
- **RAW-first:** ano.
- **Status safety:** stav je odvozen z explicitního „Žádosti od/do“; zmizení z indexu není CLOSED/CANCELLED.
- **Finance:** částky se převádějí do integer minor units.
- **Live smoke:** `scripts/smoke_plzensky_connector.py`.
