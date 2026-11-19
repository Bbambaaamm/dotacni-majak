# #510 — omezený browserový UNKNOWN → odpověď → nové posouzení

V přípravě žádosti pro vybranou výzvu se používá `GET /grants/{id}/eligibility` s owner capability v hlavičce. Každý požadavek je `no-store`; veřejný detail a tematická shoda nejsou podklady pro způsobilost. Při chybě se předchozí výsledek skryje. Odpověď API uvádí aktuální `versionId`, takže stará baseline workspace není vydávána za aktuální vyhodnocení.

Pouze když API vrátí `NEEDS_INFORMATION` a `missingAttributes` obsahuje `applicant.type`, nabídne stránka jednu otázku. Odpověď se výslovným odesláním uloží přes `PUT /applicant-profile` (jen `applicantType`) pod stejnou owner capability; ostatní serverové atributy se nemění. Místní profil v `localStorage` se automaticky nesynchronizuje. Po úspěšném zápisu se znovu čte API/D1; klient nepočítá výsledek sám. Uživatelsky deklarovaný typ nedává definitivní `ELIGIBLE` ani `INELIGIBLE`: pozitivní výsledek je `LIKELY_ELIGIBLE`, negativní `NEEDS_REVIEW`. Neznámé jiné atributy, chybějící ruleset či nepodporovaný operátor zůstávají bez progresivního formuláře.

E2E fixture je syntetické pravidlo pro testovací výzvu `grant:e2e:open` a nevyjadřuje skutečné oficiální podmínky. Browserový test ověřuje skutečný Workers API/Miniflare D1: UNKNOWN → volba obce → `LIKELY_ELIGIBLE` → externí změna profilu → `NEEDS_REVIEW`, včetně verze, evidence ID, deklarované provenance, mobilního reflow/a11y a 503 fail-closed/retry. Bez přidělené owner capability nebo pravidel nevzniká rozhodnutí.

Mimo tento slice: jiné atributy (včetně počtu obyvatel), automatická synchronizace lokálního profilu, ověřování typu z autoritativního registru, všechny zbývající operátory #300 a konečný release/human GO gate. Před podáním je třeba ověřit oficiální podmínky.
