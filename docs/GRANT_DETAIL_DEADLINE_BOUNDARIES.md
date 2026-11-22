# Detail #401: pouze doložené hranice termínu

Seznam „Termíny podle zdroje“ ukazuje „Od“ jen pro neprázdné `startsAt` a „Do“ jen pro neprázdné `endsAt` v odpovědi Detail API. `null` i prázdný/whitespace řetězec znamenají pro zobrazení chybějící hranici; zdrojová hodnota se nepřepisuje. Samostatné zahájení příjmu proto nedostává prázdné „Do“; samostatné ukončení nedostává vymyšlené „Od“. Pokud nejsou dostupné ani jedna hranice, zobrazí se výslovně neznámý termín a výzva k ověření v oficiálním zdroji. Metadata časové zóny a pravidla pro připojený/nepřipojený doklad zůstávají beze změny.

Regrese ověřuje čtyři tvary hranic unit testem a existující skutečnou D1 → API → browser fixture pro oddělené otevření a doložené ukončení na desktopu i mobilu, včetně axe/reflow. Fixture není živý důkaz aktuálního příjmu ani osobní způsobilosti. Celé #401 zůstává otevřené.
