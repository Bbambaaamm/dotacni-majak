# Detail výzvy — doložené termíny (#401, dílčí slice)

Detail zobrazuje `deadlines` aktuální `GrantCallVersion` z existujícího API. Hodnoty času zachovávají přesnost a offset z normalizovaného zdroje; `Z` je čitelně označené UTC. Datum bez času se nepřevádí na půlnoc. Pole `timezone`, pokud je jiné než UTC, se zobrazuje samostatně jako metadata zdroje, nikoli jako automaticky přepočtená hodnota.

Termín s propojeným `evidenceId` nabízí odkaz na oficiální dokument a stránku pouze tehdy, když API vrátilo odpovídající `field_evidence`. Jinak přizná nepřipojený samostatný doklad a směruje k oficiálnímu zdroji. Pokud žádné termíny nejsou normalizované a verze má datum příjmu, API vrací dosavadní syntetické `APPLICATION_WINDOW` bez předstíraného `evidenceId`; pokud není ani toto, detail explicitně uvádí neznámý termín. Zobrazení termínu/statusu není živé potvrzení otevřeného příjmu, osobní způsobilosti ani garance přijetí.

Regrese `tests/e2e/core-flow.spec.ts` ověřuje skutečnou D1/API/browser cestu, zachování UTC sekundy a odkaz na doklad stránky 2. Celé #401 zůstává otevřené: personalizovaná relevance/eligibility/finance, responsive a další stavy vyžadují samostatné reviewovatelné slice.

## Hranice finančních hodnot detailu

Klient při úspěšném HTTP 200 ověřuje vedle tvaru odpovědi také meze každého scénáře: sazby jsou celé basis points v rozsahu 0–10000, částky v minor units jsou nezáporná bezpečná celá čísla a případná dolní mez nesmí převyšovat horní. `null` znamená neznámou mez, nikoli nulu; platné 0 a 100 % zůstávají zachované. Neplatný či protichůdný scénář zneplatní celou odpověď a ukáže bezpečný chybový stav, nikoli vymyšlený finanční závěr. Jde o druhou hranici vůči chybnému API payloadu, nikoli náhradu DB CHECK a publikačního gate ani výpočet osobní podpory.

## Zachycení verze není kontrola zdroje

Rychlý přehled uvádí `capturedAt` jako „Verze výzvy zachycena“ odděleně od „Poslední pozorování záznamu u zdroje“. Druhý údaj vychází jen z `sources[].lastSeenAt` (úspěšné pozorování zdrojového záznamu, i beze změny obsahu); pokud chybí všechny záznamy, ukazuje „Není doložena“, nikoli datum zachycení jako falešné pozorování. Pozorování není verifikace podmínek právě zobrazené verze ani živé potvrzení otevřeného příjmu. Jednotlivé zdroje dále zobrazují vlastní datum pozorování. Workspace vrací `versionReview.currentCapturedAt` odděleně; historicky pojmenovaný API klíč `sourceCheckedAt` znamená pouze pozorování a při chybějícím záznamu je `null`, bez fallbacku na `captured_at`. Reálný D1/API/browser test zahrnuje verzi bez `source_records` i verzi s pozdějším pozorováním po zachycení verze.

Kalendářní datum zachycení, změny, verze a pozorování zobrazuje detail podle data uvedeného ve zdrojové časové značce, nikoli podle lokální zóny prohlížeče. Výběr nejnovějšího pozorování nadále porovnává skutečné okamžiky včetně offsetu; jen text data zachovává kalendář zdroje. Neparsovatelná nebo neplatná hodnota zůstává původním textem, nepředstírá opravený termín. Unit testy pokrývají oba směry offsetu a date-only; mobilní E2E přes skutečné D1/API a prohlížeč v `Pacific/Honolulu` ověřuje oba zdrojové záznamy, reflow a axe. Nejde o živé potvrzení aktuálnosti.
