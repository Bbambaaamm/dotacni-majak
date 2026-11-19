# Doklady u financování a požadavků (#401)

Detail výzvy zobrazuje vedle normalizovaného scénáře financování a požadavku odkaz na dokument, stránku a stav ověření, pokud `evidenceId` odpovídá důkazu v aktuální odpovědi Detail API. Odkaz vede na `sourceUrl` vrácenou API, nikoli na odhadnutou adresu. Pokud vazba chybí nebo důkaz není v omezené sadě odpovědi, text výslovně upozorní, že samostatný doklad není připojen, a odkáže uživatele na oficiální zdroj. Toto není posouzení individuální způsobilosti ani výpočet vlastní hotovosti.

Regrese používá syntetický D1 seed a skutečný API/DB → browser tok; ověřuje oba kontextové odkazy, chybějící doklad, mobilní reflow a automatickou a11y kontrolu. Syntetická částka není fakt o reálné výzvě. Důkazy z oficiálních zdrojů zůstávají rozhodující; limit API (100 evidence rows) může mít za následek explicitní stav bez připojeného dokladu.
