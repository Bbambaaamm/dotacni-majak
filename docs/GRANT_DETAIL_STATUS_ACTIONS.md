# Detail výzvy: další krok podle kanonického stavu (#401)

Detail nabízí akci k přípravě žádosti pouze pro stav `OPEN` v zachycené verzi. Ani tento stav není živým potvrzením, že lze právě podat žádost; termín a podmínky je nutné ověřit u poskytovatele. `PLANNED` a `ANNOUNCED` vedou k ověření zahájení příjmu; `PAUSED` k ověření obnovy; `CLOSED` k ověření případného dalšího kola; `CANCELLED` k ověření rozhodnutí. Ostatní či neznámé stavy neotevírají aktivní žádost. Odkaz na projekt se u těchto stavů nenabízí, protože cílová stránka vytváří přípravu žádosti, nikoli automatické sledování výzvy.

Vyhledávání, detail i modelová karta na úvodní stránce zobrazují `OPEN` jako „Otevřeno v zachycené verzi“ a přímo vybízejí k ověření aktuálního stavu v oficiálním zdroji před podáním. Hodnota API `OPEN` a chování filtru se nemění; uzávěrka ani chybějící zdrojový záznam samy nepřepisují kanonický stav na `CLOSED` nebo `CANCELLED`.

Primární sticky akce pro neotevřené stavy vede na oficiální detail výzvy, pokud jej API poskytne; jinak vede zpět na hledání dalších výzev. Stav zdrojového záznamu `MISSING_CANDIDATE`/`CONFIRMED_MISSING` nijak nemění kanonický stav výzvy a nikdy sám neimplikuje zrušení. Testy používají skutečnou lokální D1, API a mobilní Chromium pro hranice stavů; source-presence OPEN je samostatná negativní kontrola.

Detail pro kanonické `DRAFT` a `ARCHIVED` zobrazuje srozumitelné štítky „Návrh výzvy (příjem není potvrzen)“ a „Archivní záznam výzvy (příjem není potvrzen)“ místo interních kódů. Ani jeden stav nevytváří možnost aktivní žádosti; změna je pouze prezentační. Mobilní E2E ověřuje ARCHIVED nad skutečnou D1/API odpovědí.

## Kontext způsobilosti na veřejném detailu

Veřejný detail nemá vlastnickou capability ani údaje konkrétního projektu, proto nikdy neprezentuje osobní verdikt způsobilosti. Výslovně odděluje tematickou shodu a zveřejněné požadavky od vyhodnocení známých pravidel aktuální verze proti projektu. Chybějící údaj je UNKNOWN, nikoli FAIL. Pouze u kanonicky `OPEN` výzvy odkazuje do existujícího anonymního projektového toku (`/projekty` s názvem a identitou výzvy, bez capability v URL); až tam chráněné API s owner capability načítá skutečný stav pravidel. Pokud pravidla chybí, projekt to přiznává. Ostatní stavy místo přípravy žádosti vyzývají k ověření aktuálního stavu u poskytovatele. E2E test ověřuje skutečnou D1/API cestu přes projekt a mobilní hranice stavů; nejde o potvrzení správnosti pravidel poskytovatele.
