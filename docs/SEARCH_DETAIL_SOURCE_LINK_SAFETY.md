# Oficiální odkazy v search a detailu (#400/#401)

URL uložená v canonical verzi, source recordu, evidenci nebo profilu poskytovatele je obsah zdroje, nikoli bezpečný atribut HTML odkazu. UI ji nemění v databázi ani z ní neodvozuje stav výzvy. Klikací odkaz dovolí jen absolutní HTTP(S) URL bez přihlašovacích údajů, okrajových bílých znaků a řídicích znaků. Relativní, `javascript:`, `data:` a jiné protokoly zůstanou neklikatelné. Na kartě se takový odkaz neobjeví a uživatel dostane textové upozornění s cestou na detail; v detailu zůstává obsah dokladu viditelný s upozorněním, že odkaz není bezpečně dostupný.

Primární odkaz detailu vybírá bezpečnou URL verze, poté bezpečnou URL zdrojového záznamu a až pak web poskytovatele. Pokud zbývá pouze web poskytovatele, text výslovně říká, že konkrétní odkaz na výzvu není doložen. Chybějící či vadný odkaz není důkaz zrušení, nezpůsobilosti ani neexistence výzvy. Uživatel má ověřit aktuální podmínky u poskytovatele.

Unit testy pokrývají povolené a odmítnuté URL. Browser regresní test používá syntetickou nebezpečnou URL ve skutečném D1 seed záznamu a ověřuje API, desktop/mobil, absenci klikacího nebezpečného odkazu, bezpečný fallback, axe a reflow. Ostatní legitimní odkazy ověřují existující full-stack scénáře.
