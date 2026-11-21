# Datum změny na detailu (#401, dílčí slice)

Datum `change_events.created_at` pochází z detailového API a není samo o sobě potvrzením aktuálních podmínek výzvy. Detail zachovává neznámý či chybný text data a přidává viditelné upozornění: datum události ani pořadí seznamu podle takového údaje nelze ověřit. Neodvozuje z něj zrušení, uzavření ani možnost podat žádost; rozhodují oficiální podmínky poskytovatele.

Regrese pokrývá platné datum a dva neověřitelné tvary v unit testu; syntetická položka v lokální D1 prochází Detail API a mobilním Chromium včetně axe a reflow. Nejde o živé potvrzení zdroje, o úplné posouzení změn ani o uzavření celého #401.

Seznam posledních změn nově zobrazuje česky všech devět kanonických typů změny; neznámý typ neinterpretuje a vyzývá k ověření u zdroje. Případná `fieldPath` zůstává dohledatelná jako interní označení pole, nikoli jako uživatelsky doložený popis změny. Datum, pořadí, závažnost ani staré/nové hodnoty tento prezentační slice nemění. Unit test ověřuje celou kanonickou množinu a bezpečný fallback; mobilní E2E potvrzuje skutečný D1 → API → zobrazený typ `OTHER` i označení interní cesty s axe/reflow. Zdroj a aktuální podmínky je stále nutné ověřit u poskytovatele.
