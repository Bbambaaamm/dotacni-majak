# Search: rozhodovací identity karet (#400, dílčí slice)

Klient odmítne i úspěšný Search API 200, pokud má kterákoli karta pouze bílé znaky v `grantCallVersionId` nebo `grantCallId`. Prázdná identita nemůže být bezpečným odkazem na kanonickou aktuální verzi ani stabilní výzvu. Hodnoty se neořezávají ani neopravují; první stránka skryje výsledky a nabídne opakování, pokračování zachová starší karty a původní cursor. Již existující validace odmítá prázdný titulek a poskytovatele. Nejde o doklad aktuálního oficiálního zdroje, snapshot indexu nebo osobní způsobilosti.

Unit regrese pokrývá obě identity; mobilní full-stack E2E jednorázově mění vždy právě jednu identitu ve skutečné D1/API odpovědi, pak ověřuje retry proti nezměněnému API, axe a reflow. Celé #400 zůstává otevřené.
