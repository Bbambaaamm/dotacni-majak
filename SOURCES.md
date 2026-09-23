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


## Karlovarský kraj — dotační programy

- **Oficiální zdroj:** https://www.kr-karlovarsky.cz/dotace/dotacni-programy-karlovarskeho-kraje
- **Discovery:** veřejný server-rendered katalog s pagination `?page=N`.
- **Identity:** stabilní detailní URL `/dotace/{slug}` + deterministický source ID.
- **Detail:** explicitní provider status, termíny příjmu, oblast, kontakt a oficiální dokumenty.
- **Connector:** `connectors/karlovarsky`.
- **RAW-first:** ano.
- **Safety:** neveřejný/přihlašovací RAP systém se nescrapuje; status se mapuje z explicitního textu webu; disappearance není cancellation.
- **Live smoke:** `scripts/smoke_karlovarsky_connector.py`.


## Plzeňský kraj — eDotace

- **Oficiální zdroj:** https://dotace.plzensky-kraj.cz/verejnost
- **Discovery:** veřejné JSON gridy eDotace pro otevřené a připravované dotační tituly.
- **Stable source identity:** číselné ID z URL `/verejnost/dotacnititul/{id}/`.
- **Detail:** účel, důvod, potenciální žadatelé, explicitní termíny, finance, administrátoři a přílohy.
- **Connector:** `connectors/plzensky`.
- **RAW-first:** ano.
- **Status safety:** stav je odvozen z explicitních termínů „Žádosti od/do“; zmizení z indexu není CLOSED/CANCELLED.
- **Finance:** částky se převádějí do integer minor units.
- **Live smoke:** `scripts/smoke_plzensky_connector.py`.


## Jihočeský kraj — vyhlášené dotace

- **Oficiální zdroj:** https://www.kraj-jihocesky.cz/ku_dotace/vyhlasene
- **Discovery:** jedna veřejná server-rendered stránka s aktuálně vyhlášenými programy.
- **Obsah:** název, charakteristika, harmonogram, aplikační odkaz a soubory.
- **Identity:** deterministická kombinace data zveřejnění a názvu; poskytovatel na stránce nepublikuje samostatné veřejné ID položky.
- **Connector:** `connectors/jihocesky`.
- **RAW-first:** ano; jedna discovery stránka = jeden sdílený RAW snapshot pro nalezené records.
- **Status safety:** stav pouze z explicitního Harmonogramu; disappearance není CLOSED/CANCELLED.
- **Region:** CZ031.
- **Live smoke:** `scripts/smoke_jihocesky_connector.py`.


## Liberecký kraj — Dotace

- **Oficiální zdroj:** https://dotace.kraj-lbc.cz/
- **Discovery:** veřejný rozcestník oblastí → veřejné seznamy programů → detail programu s veřejným číselným `d<ID>`.
- **Detail:** vyhlášení, zahájení, ukončení, aktuální popis, případná explicitní alokace a oficiální soubory.
- **Connector:** `connectors/liberecky`.
- **RAW-first:** ano.
- **Safety:** záštity bez finanční podpory jsou vyřazeny; login/Identity občana se neautomatizuje; disappearance není cancellation.
- **Region:** CZ051.
- **Live smoke:** `scripts/smoke_liberecky_connector.py`.


## Ústecký kraj — programové dotace

- **Oficiální vstup:** https://www.kr-ustecky.cz/dotace
- **Discovery:** veřejné server-rendered seznamy „Programové dotace Ústeckého kraje“ pro jednotlivé oblasti + přímé programové odkazy oblasti informatiky/IZS.
- **Detail:** kód výzvy, oblast, alokace, explicitní sběr žádostí, stav, typ žadatele a materiály.
- **Connector:** `connectors/ustecky`.
- **RAW-first:** ano.
- **Status safety:** explicitní provider status a termíny mají přednost; disappearance není CLOSED/CANCELLED.
- **Aplikační portál:** pouze odkaz; přihlášený Portál dotací a služeb se nescrapuje.
- **Region:** CZ042.
- **Live smoke:** `scripts/smoke_ustecky_connector.py`.


## Moravskoslezský kraj — regionální dotační programy

- Oficiální veřejný index: https://www.msk.cz/cs/temata/dotace/
- Detail programu: veřejné stránky `/cs/temata/dotace/<slug>-<numeric-id>/`
- Detail veřejně uvádí termíny, často kód programu, podmínky a přílohy.
- Connector nescrapuje ePodatelnu.
- RAW-first, disappearance != cancellation.
- Pokud stránka publikuje více kol podání, connector je nespojuje do falešného kontinuálního intervalu.
- Region: CZ080.


## Olomoucký kraj — krajské dotační programy 2026
- Aktuální programy: https://www.olkraj.cz/dotace-granty-prispevky-krajske-dotacni-programy-2026/aktualni-dotacni-programy
- Ukončené programy: https://www.olkraj.cz/dotace-granty-prispevky-krajske-dotacni-programy-2026/ukoncene-dotacni-programy
- Veřejný detail publikuje název, anotaci, termín příjmu, oprávněné žadatele, pravidla a RAP odkaz.
- RAP se pouze odkazuje; Maják jej nescrapuje.
- Aktuální/ukončený index je explicitní status signál; disappearance != cancellation.
- Region: CZ071.


## Zlínský kraj — regionální dotační programy
- Oficiální index: https://zlinskykraj.cz/dotace
- Detailní stránky publikují kód programu, datum vyhlášení, interval příjmu, alokaci, oblast a dokumenty.
- Elektronické formuláře se pouze odkazují; Maják je nescrapuje.
- Region: CZ072.


## Jihomoravský kraj — dotační portál
- Dotační oblasti: https://dotace.kr-jihomoravsky.cz/Oblasti.aspx
- Discovery: veřejné oblastní seznamy `/Folders/...aspx` → detail programu `/Grants/<id>-...aspx`.
- Veřejný detail publikuje alokaci, účel, termín příjmu, lokalizaci a u titulů také příjemce, min/max podporu a spoluúčast.
- Stav konkrétní žádosti ani Portál obcí se nescrapuje.
- Stable source ID = číselné ID detailu.
- Region: CZ064.


## Pardubický kraj — Dotační portál

- **Oficiální zdroj:** https://dotace.pardubickykraj.cz/grants
- **Discovery:** veřejný server-rendered katalog programů.
- **Identity:** stabilní UUID nebo historické číselné ID z detail URL `/grants/<id>`.
- **Detail:** cíl/popisy, oprávnění žadatelé, min/max dotace, spoluúčast, application window a oficiální přílohy.
- **Connector:** `connectors/pardubicky`.
- **RAW-first:** ano.
- **Safety:** detailní explicitní termíny mají přednost; disappearance není cancellation; přihlášení/odeslání žádosti se neautomatizuje.
- **Conditional finance:** různé sazby spoluúčasti pro různé typy žadatelů se neslučují do jedné univerzální hodnoty.
- **Region:** CZ053.
- **Live smoke:** `scripts/smoke_pardubicky_connector.py`.
- **Aktuální provozní caveat (2026-09-23):** GitHub-hosted Ubuntu runner hlásí při TLS handshaku `CERTIFICATE_VERIFY_FAILED` pro veřejný portál. TLS ověřování se **nevypíná**. PR fixture CI zůstává gating; PR live smoke toleruje pouze explicitní `UNAVAILABLE`, zatímco scheduled/manual smoke zůstává strict a tím udržuje problém viditelný v Source Health.


## Jednotný dotační portál MF (JDP)

- **Oficiální veřejný portál:** https://jdp2.mf.gov.cz/
- **Public API discovery:** `POST /jdp_api/api/nxwebedppublicdashboard/kodyvyzva`.
- **Health/status:** `GET /jdp_api/api/NxWebEDPPublicDashboard/KodyVyzvaStav`.
- **Connector:** `connectors/jdp`.
- **RAW-first:** ano; každá API discovery page se ukládá jako immutable RAW snapshot.
- **Stable source identity:** veřejné UUID pole `id`.
- **Veřejná metadata:** kód, název, popis, stav, termíny, min/max podpora, alokace, max. míra podpory jako source value a typ nástroje.
- **Aktuální coverage:** první verze záměrně ingestuje pouze veřejně **Otevřené / Běžící** výzvy přes request template pozorovaný na veřejné homepage. Ostatní stavy neodhadujeme.
- **Finance safety:** částky se převádějí do integer minor units; `miraPodporaZadostMax` zůstává source value, dokud centrální finance normalization nepotvrdí scale/jednotku.
- **Safety:** žádné přihlášení, podávání žádostí ani privátní API; disappearance není cancellation.
- **Live smoke:** `scripts/smoke_jdp_connector.py`.
