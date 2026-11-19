# Detail výzvy — doložené termíny (#401, dílčí slice)

Detail zobrazuje `deadlines` aktuální `GrantCallVersion` z existujícího API. Hodnoty času zachovávají přesnost a offset z normalizovaného zdroje; `Z` je čitelně označené UTC. Datum bez času se nepřevádí na půlnoc. Pole `timezone`, pokud je jiné než UTC, se zobrazuje samostatně jako metadata zdroje, nikoli jako automaticky přepočtená hodnota.

Termín s propojeným `evidenceId` nabízí odkaz na oficiální dokument a stránku pouze tehdy, když API vrátilo odpovídající `field_evidence`. Jinak přizná nepřipojený samostatný doklad a směruje k oficiálnímu zdroji. Pokud žádné termíny nejsou normalizované a verze má datum příjmu, API vrací dosavadní syntetické `APPLICATION_WINDOW` bez předstíraného `evidenceId`; pokud není ani toto, detail explicitně uvádí neznámý termín. Zobrazení termínu/statusu není živé potvrzení otevřeného příjmu, osobní způsobilosti ani garance přijetí.

Regrese `tests/e2e/core-flow.spec.ts` ověřuje skutečnou D1/API/browser cestu, zachování UTC sekundy a odkaz na doklad stránky 2. Celé #401 zůstává otevřené: personalizovaná relevance/eligibility/finance, responsive a další stavy vyžadují samostatné reviewovatelné slice.
