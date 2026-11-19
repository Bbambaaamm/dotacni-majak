# Detail výzvy: obnovení po chybě načtení (#401)

Pokud první načtení detailu z API selže, obrazovka nezobrazuje podmínky,
provenance ani akci „Chci tuto dotaci“. Nabídne opětovné načtení stejného ID;
při dalším pokusu znovu získá data z API. Výsledek 404 má odlišnou zprávu
(„v aktuálním indexu nenašli“) a nevybízí k opakování dočasného výpadku.
Neplatná adresa nemá retry. Při odchodu z obrazovky je request zrušen a
opožděný úspěch nesmí obnovit starý detail.

Regresní důkaz: `npm run web:e2e -- --grep 'detail API outage|missing detail'`
spouští skutečné API/D1; browserová route mění pouze odpověď prvního
nedostupného pokusu (503) a zkoušku 404. Úspěšné opakování jde do skutečného
API/D1 a kontroluje oficiální odkaz. Tento slice nedokazuje osobní
způsobilost ani aktuálnost oficiálního zdroje.
