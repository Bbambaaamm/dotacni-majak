# Detail výzvy: obnovení po chybě načtení (#401)

Pokud první načtení detailu z API selže, obrazovka nezobrazuje podmínky,
provenance ani akci „Chci tuto dotaci“. Nabídne opětovné načtení stejného ID;
při dalším pokusu znovu získá data z API. Výsledek 404 má odlišnou zprávu
(„v aktuálním indexu nenašli“) a nevybízí k opakování dočasného výpadku.
Neplatná adresa nemá retry. Při odchodu z obrazovky je request zrušen a
opožděný úspěch nesmí obnovit starý detail.

Regresní důkaz: `npm run web:e2e -- --grep 'detail retry|missing detail'`
spouští skutečné API/D1; browserová route mění pouze odpovědi nedostupného
pokusu (503) a zkoušku 404. Úspěšné opakování jde do skutečného API/D1 a
kontroluje oficiální odkaz. Po klávesnicovém opakování zůstává tlačítko při
načítání focusovatelné (s `aria-disabled` a `aria-busy`), další aktivace
nespustí paralelní request. Po další chybě zůstává focus na retry, po úspěchu
přejde na titulek načtené výzvy; pokud uživatel během čekání přejde na jiný
prvek, focus se mu nepřesune. Mobilní E2E kontroluje také reflow a axe.
Tento slice nedokazuje osobní způsobilost ani aktuálnost oficiálního zdroje.

## Konzistence příznaků dostupnosti

Detail API odvozuje `availability.funding`, `availability.requirements` a
`availability.evidence` od neprázdnosti příslušných seznamů pro zachycenou
verzi. Klient HTTP 200 s opačným příznakem odmítne jako neplatný celek,
nezobrazí požadavky ani CTA přípravy a dovolí bezpečný retry. `UNKNOWN`
znamená chybějící normalizované položky, nikoli nesplnění podmínek; prázdný
seznam dokladů odpovídá `SOURCE_ONLY`, ne tvrzení o ověření. Unit regrese
pokrývá obě strany všech tří rozporů; mobilní E2E mění pouze příznak jedné
skutečné D1/API odpovědi, retry pak načte nezměněný skutečný API detail a
kontroluje a11y/reflow. Nejde o ověření správnosti oficiálních podmínek.

## Vazba aktuální verze na zobrazená tvrzení

Detail API vrací horní souhrn zachycené verze a nejvýše 20 historických verzí.
Klient odmítne HTTP 200, pokud v omezeném seznamu není právě jedna položka
`isCurrent`, její ID/číslo/čas zachycení/stav/ověření/uzávěrka neodpovídají
hornímu souhrnu nebo se v seznamu opakuje ID či číslo verze. Tím nelze
zobrazit stav „aktuální“ vedle rozporné historie a nabídnout přípravu žádosti
na základě nejednoznačné odpovědi; vznikne bezpečná chyba s možností retry.
Historie zůstává omezená API a tento test neověřuje aktuální dostupnost
výzvy u poskytovatele. Unit test pokrývá jednotlivé rozpory, mobilní browser
regrese upraví jen odpověď skutečné D1/API výzvy a retry jde na nezměněnou
D1/API odpověď včetně axe/reflow.
