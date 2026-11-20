# Doklady u financování a požadavků (#401)

Detail výzvy zobrazuje vedle normalizovaného scénáře financování a požadavku odkaz na dokument, stránku a stav ověření, pokud `evidenceId` odpovídá důkazu v aktuální odpovědi Detail API. Odkaz vede na `sourceUrl` vrácenou API, nikoli na odhadnutou adresu. Pokud vazba chybí nebo důkaz není v omezené sadě odpovědi, text výslovně upozorní, že samostatný doklad není připojen, a odkáže uživatele na oficiální zdroj. Toto není posouzení individuální způsobilosti ani výpočet vlastní hotovosti.

Regrese používá syntetický D1 seed a skutečný API/DB → browser tok; ověřuje oba kontextové odkazy, chybějící doklad, mobilní reflow a automatickou a11y kontrolu. Syntetická částka není fakt o reálné výzvě. Důkazy z oficiálních zdrojů zůstávají rozhodující; limit API (100 evidence rows) může mít za následek explicitní stav bez připojeného dokladu.

Detail nyní ukazuje všech nejvýše 100 dokladů vrácených Detail API (dříve skryl vše za prvních 20). Při přesně 100 záznamech výslovně sděluje, že API má limit a další doklady mohou existovat; neoznačuje seznam za úplný. Syntetický D1 seed se 101 doklady ověřuje skutečný API cap, browser-visible poslední zobrazený doklad, mobilní reflow a a11y. Limit API a chybějící doklad nad limitem zůstávají známým omezením, nikoli důvodem považovat podmínky za splněné.

Při fresh CI odhalil navazující mobilní test vyhledávání závod: opožděný `toggle` již odpojeného panelu mohl po obnovení výsledků přepsat stav nového panelu a skrýt řazení. Handler nyní přijímá událost jen od aktuálně připojeného panelu; E2E čeká na nové výsledky místo čtení starého DOM a znovu ověřuje viditelnost řazení. Jde o úzkou stabilizaci nutnou pro zelený gate, nikoli změnu parametrů vyhledávání.
