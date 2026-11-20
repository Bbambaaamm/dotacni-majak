# Detail výzvy: další krok podle kanonického stavu (#401)

Detail nabízí akci k přípravě žádosti pouze pro stav `OPEN` v zachycené verzi. Ani tento stav není živým potvrzením, že lze právě podat žádost; termín a podmínky je nutné ověřit u poskytovatele. `PLANNED` a `ANNOUNCED` vedou k ověření zahájení příjmu; `PAUSED` k ověření obnovy; `CLOSED` k ověření případného dalšího kola; `CANCELLED` k ověření rozhodnutí. Ostatní či neznámé stavy neotevírají aktivní žádost. Všechny lze uložit k projektu pro sledování, nikoli tím potvrdit způsobilost.

Primární sticky akce pro neotevřené stavy vede na oficiální detail výzvy, pokud jej API poskytne; jinak nabízí uložení k projektu. Stav zdrojového záznamu `MISSING_CANDIDATE`/`CONFIRMED_MISSING` nijak nemění kanonický stav výzvy a nikdy sám neimplikuje zrušení. Testy používají skutečnou lokální D1, API a mobilní Chromium pro hranice stavů; source-presence OPEN je samostatná negativní kontrola.
