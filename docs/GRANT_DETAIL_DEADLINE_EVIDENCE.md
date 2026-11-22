# Ověření dokladu termínu v detailu (#401)

U normalizovaného termínu, který odkazuje na samostatný doklad dostupný v detail API, se vedle odkazu zobrazuje stav ověření doloženého údaje (`FieldEvidence.verificationStatus`). Odkaz na dokument sám o sobě neznamená, že termín byl ověřen; status se nevypočítává z existence odkazu ani z data stažení dokumentu.

Bez připojeného dokladu nebo při dokladu mimo omezený seznam detail výslovně vybízí k ověření u poskytovatele. Datum termínu a datum pozorování zdroje nejsou zárukou, že lze aktuálně podat žádost. Tato úprava nemění zdrojová data, jejich verze, API ani eligibility.

Regrese: `tests/e2e/core-flow.spec.ts` ověřuje vazbu termín–doklad–stav na skutečné D1/API odpovědi a viditelný stav v prohlížeči; chybějící doklad zůstává bez vymyšleného ověření.
