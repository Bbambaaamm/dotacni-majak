# Agent Handoff — Dotační maják

Tento dokument je vstupní instrukce pro AI agenta, který pokračuje ve vývoji.

## Mise
Buduj **Dotační maják — Najde. Pohlídá. Dotáhne.** jako důvěryhodnou open-source veřejnou službu pro české uživatele.

## Orchestrace projektu
- Root completion program je GitHub issue **#662** (`HERDR CONTROL · Dotační maják completion program → MVP → Beta → v1.0`).
- **Herdr** je execution/policy control plane; **dotacni-majak-hermes** je stabilní persistent parent/coordinator.
- Hermes před každým slice znovu načte `main`, otevřené PR/issue, readiness/roadmap a durable evidence; nesmí duplikovat již běžící práci.
- Hermes volí nejbližší dependency-safe kritický slice, deleguje bounded child nodes a po merge ihned replanuje další krok.
- Child agenti implementují/researchují/testují/reviewují v izolovaných worktree; permissions child ⊆ parent.
- Merge gate: testy → zelené CI/security/dependency kontroly → independent review PASS na přesném head SHA → ověřit nezměněný head → merge.
- Pozdější milestone nesmí předběhnout otevřený P0 dependency blocker jen proto, že má novější issue číslo.
- Bez lidského zásahu pokračuj autonomně; zastav na credential/billing/production-deploy/irreversible-action, skutečně neřešitelném bezpečnostním/produktovém blockeru **a na každém explicitním human release gate**.
- Public Beta ani v1.0 nesmí Hermes sám prohlásit za schválené: pokud gate vyžaduje reálné uživatelské/usability evidence, manuální audit, lidského reviewera nebo explicitní GO/NO-GO rozhodnutí, připrav všechny automatizovatelné podklady a pak eskaluj člověku bez fabrikace důkazů.
- Root issue #662 zůstává otevřený až do splnění Public Beta a **#41 v1.0 production readiness gate**.

## Před prací vždy přečti
1. README.md
2. ARCHITECTURE.md
3. DATA_MODEL.md
4. SOURCE_ADAPTERS.md
5. INGESTION.md
6. ROADMAP.md
7. docs/ISSUE_ROADMAP.md
8. docs/PRODUCT_SPEC.md
9. docs/UX_PRINCIPLES.md
10. DESIGN_SYSTEM.md
11. relevantní ADR

## Priorita při konfliktu
1. přesnost dotačních údajů
2. provenance
3. bezpečnost
4. ochrana proti falešným závěrům
5. vysvětlitelnost
6. end-to-end vyřešení uživatelova problému
7. jednoduchost/accessibility
8. spolehlivost
9. zero-cost
10. výkon
11. počet funkcí

## Nezpochybnitelné invariants
- official source = source of truth,
- UNKNOWN != FAIL,
- relevance != eligibility; detail výzvy bez samostatného match-reason API nesmí vydávat URL parametr `intent` / `returnResult` za doloženou shodu. Vysvětlení konkrétní tematické shody je na výsledkové kartě, pokud se výzva v novém hledání stále zobrazuje; přímý detail ukazuje jen cestu zpět k hledání.
- AI není jediný rozhodovací mechanismus,
- finance/rules jsou deterministické,
- immutable versioning,
- Srovnatelně obrácené zdrojové termíny v detailu ponechat beze změny a upozornit na rozpor (datum proti datu, čas s offsetem proti času s offsetem); neznámé/chybné/nesouměrně přesné hodnoty nejsou potvrzený interval. Syntetický D1/API browser test pro #401 ověřuje dílčí trust slice, nikoli celkovou akceptaci detailu,
- RAW-first,
- provenance u kritických tvrzení,
- disappearance != cancellation,
- parser failure nesmí provést destructive changes,
- na první stránce `indexState=EMPTY` znamená prázdný index jen s explicitními nulovými facet counts; `facets=null` znamená nedostupné počty, nikoli důkaz prázdného indexu. Na pokračovací stránce jsou facety běžně `null`, ale `EMPTY` s cursorem není platný výsledek,
- žádný auto-pay,
- každý klíčový screen má „Co mám udělat teď?“.

## Vývojový workflow
- pracuj přes issue → branch → PR,
- malé reviewovatelné PR,
- tests + CI,
- connector používá fixtures,
- live smoke test odděleně,
- canonical schema měň jen přes ADR/review,
- po merge navazuj z čerstvého main; nepokračuj stacked historií přes squash bez vyčištění.

## Validace odpovědi vyhledávání
Klient výsledků kontroluje úspěšnou odpověď Search API před vykreslením: záměr musí odpovídat požadavku, seznam výsledků, stránkovací kurzor a facets musí mít smluvený tvar. Stav `EMPTY` nesmí obsahovat výsledky ani další stránku; karta musí mít neprázdnou identitu, název a poskytovatele a aktivní stav (`OPEN`, `PLANNED`, `ANNOUNCED`). Neplatná či neúplná odpověď se zobrazí jako chyba s možností opakování; nesmí být vydávána za prázdný katalog nebo za konec stránkování.

Karta smí vysvětlovat shodu přes širší význam (`ONTOLOGY`) jen tehdy, když úspěšná odpověď Search API obsahuje alespoň jeden neprázdný rozšířený pojem. Další stránka musí vracet stejné rozšířené pojmy jako první (jinak by připojené karty neměly odpovídající vysvětlení). Při rozporu klient nezobrazí nové karty a umožní bezpečné opakování; tematická shoda není způsobilost.

Karta výsledku přebírá `capturedAt` a `verificationStatus` přímo z aktuální indexované neměnné verze výzvy. Datum je čas zachycení, nikoli poslední kontrola; stav ověření se vztahuje k této verzi. Karta výslovně upozorňuje, že tyto údaje nepotvrzují dnešní podmínky ani příjem žádostí. Chybějící, neplatné nebo neznámé hodnoty klient odmítá jako neplatnou odpověď. Tato dílčí úprava neuzavírá #400.

## Neměnné filtry výsledků

Na šířce do 800 px otevřený panel filtrů funguje jako pojmenovaný modální sheet: ostatní obsah je inertní, Tab/Shift+Tab zůstává uvnitř, Escape i viditelné tlačítko zavřou panel a vrátí fokus na spouštěcí souhrn. Zavřený panel nemá dostupné interaktivní prvky. Otevřený stav se zachová při skutečné změně filtru a novém dotazu; desktopový `details` zůstává běžným rozbalovacím panelem. Regresní test pokrývá lokální D1 → skutečné Search API → mobilní Chromium včetně axe a reflow. Jde o úzký UX slice #400, nikoli o potvrzení aktuálnosti zdrojů.

Při opětovném výběru již aktivního stavu výzvy nebo dostupnosti termínu nesmí klient znovu zahájit hledání: načtené karty, otevřený mobilní panel filtrů a fokus zůstávají beze změny. Skutečná změna filtru stále obnoví první stránku ze Search API. Regrese je ověřena přes lokální D1 → skutečné API → mobilní Chromium, včetně počtu síťových požadavků. Dílčí úprava neuzavírá #400.

Při stránkování vrací Search API facety jen na první stránce; pokračování má `facets: null`. Klient odmítá pokračování s vloženými počty filtrů jako neplatnou odpověď, ponechá již načtené karty a nabídne opakování. Nulové nebo nedostupné počty tím nevyvozuje z dalších stránek. Regrese používá lokální D1 → skutečné API → mobilní Chromium s kontrolou axe/reflow. Jde o dílčí #400, nikoli potvrzení aktuálnosti oficiálních zdrojů.

## Validace detailu výzvy
Klient detailu ověřuje úspěšnou odpověď API před vykreslením: identita výzvy musí odpovídat požadavku, základní verze, poskytovatel, dostupnost, zdroje, podmínky, scénáře a doklady musí mít smluvený tvar. Titul, ID aktuální verze a jména poskytovatele a programu nesmějí být prázdná ani jen whitespace; 200 s prázdnou identitou či atribucí se zobrazí jako chyba s možností opakování, ne jako ověřený detail. Chybějící či poškozený údaj se nesmí vykreslit jako ověřená podmínka nebo nulový počet dokladů; zobrazí se chyba s možností opakování. HTTP 404 zůstává odlišné od poškozené úspěšné odpovědi.

## Návrat z detailu do vyhledávání
Detail přenáší v URL pouze ověřené parametry záměru, aktivních API filtrů a řazení. Zpětný odkaz obnoví filtry a první stránku výsledků novým požadavkem na API. Stránkovací kurzor ani dříve načtené stránky se neukládají a po návratu se neobnovují.

## Doklady v detailu výzvy
Detail API vrací nejvýše 100 dokladů. Pokud termín, scénář financování nebo požadavek odkazuje na `evidenceId`, který v omezeném seznamu chybí, UI uvede, že doklad není v tomto seznamu dostupný, a vyzve k ověření v oficiálním zdroji. Pouze `evidenceId: null` znamená, že samostatný doklad není připojen. Chybějícímu dokladu UI nepřiřazuje název, odkaz ani stav ověření.

## Omezené seznamy v detailu výzvy
Detail API vrací nejvýše 20 zdrojových záznamů, 20 změn a 20 verzí. Při dosažení limitu UI upozorní, že seznam nemusí být úplný. Zobrazených 20 chybějících zdrojových záznamů nevylučuje další záznam se stavem `SEEN`; chybění samo o sobě neznamená zrušení výzvy. E2E fixture `grant:e2e:history` obsahuje 21 zdrojových záznamů (poslední v řazení je `SEEN`) a 21 změn mezi verzemi 21 a 22 pro ověření těchto hranic v reálném D1/API/Chromium běhu.

## Termíny v detailu výzvy
Rychlý přehled i jednotlivé termíny zachovávají přesnost a časovou zónu zdroje. Pokud neprázdný zdrojový údaj není rozpoznatelným datem/časem, zobrazí se beze změny s výslovnou výzvou k ověření u oficiálního zdroje; chybějící (`null`) údaj zůstává neznámý a nedostává varování o poškozeném formátu. Syntetický termín v E2E D1 fixture ověřuje tuto hranici přes skutečné Detail API a mobilní prohlížeč.

## Poslední pozorování zdrojového záznamu
Rychlý přehled vybírá nejnovější rozpoznatelné pozorování podle okamžiku, ale chybně formátovaná data nepovyšuje na doloženou aktuálnost. Pokud některý z omezeného seznamu zdrojových záznamů obsahuje neověřitelné datum (včetně kalendářně nemožného dne), zobrazí upozornění u souhrnu i příslušného záznamu; souhrnný datum pak nemusí být skutečně nejnovější. Nepřítomnost validního pozorování není důkaz zrušení výzvy. Syntetický zdroj `grant:e2e:page:20` ověřuje skutečné Detail API/D1 a mobilní prohlížeč.

## Metadata zachycení a stažení v detailu
Datum zachycení aktuální/historické verze a datum stažení dokladu se zobrazuje se zachováním původní hodnoty. Kalendářně nemožná nebo nerozpoznatelná hodnota dostává samostatné textové upozornění: sama nedokládá aktuálnost verze ani dokladu. Chybný formát není UNKNOWN podmínky ani důkaz zrušení výzvy. Syntetický doklad `grant:e2e:unsafe-url` ověřuje hranici přes skutečnou D1, Detail API a mobilní Chromium; zůstává pouze testovacím údajem.

## Akce z detailu výzvy
OPEN je zachycený stav, nikoli potvrzení živého příjmu nebo osobní způsobilosti. Horní i mobilní sticky akce používají stejné „Přidat k projektu“ pro GRANT i negrantový nástroj; až projekt může vyhodnotit známé podmínky. Nepoužívat zde „Chci tuto dotaci“ ani z negrantového nástroje dovozovat dotaci. Neotevřené stavy vedou na ověření u poskytovatele nebo zpět k hledání. Syntetická OPEN úvěrová verze v D1 fixture ověřuje skutečné API a mobilní prohlížeč, bez tvrzení o reálné výzvě.

## Finanční částky v detailu
Detail výzvy zobrazuje celočíselné `amount_minor` podle počtu desetinných míst měny (např. JPY 0, CZK 2, KWD 3), nikoli vždy dělené 100. Používá stejný formátovací kontrakt jako sdílený projekt. Neplatnou měnu nebo nebezpečně velké číslo nevydává za částku v hlavních jednotkách; chybějící částka zůstává „Není uvedeno“. Izolovaná syntetická JPY verze v E2E fixture dokládá cestu D1 → Detail API → mobilní prohlížeč; nejde o skutečnou nabídku podpory ani o výpočet individuální spoluúčasti. Dílčí úprava neuzavírá #401.

## Finance/detail — partial #401 slice

Detail čte dolní i horní mez dotace z již existujícího `grantAmountMinMinor` / `grantAmountMaxMinor`. U scénáře s pouze dolní mezí výslovně říká, že horní mez není uvedena; nejde o individuální příslib ani vypočtenou potřebu vlastních zdrojů. Non-grant scénáře nadále nezobrazují grantové částky. Ověření zahrnuje unit test a syntetickou D1 → skutečné Detail API → mobilní Chromium cestu s kontrolou accessibility. Celkové #401 a release gate zůstávají otevřené.

## Konzistence počtů filtrů výsledků — dílčí #400
Na první stránce bez filtru stavu a dostupnosti termínu počítá Search API obě skupiny facetů ze stejné množiny shod. Pokud součet stavů a součet dostupnosti termínu nesouhlasí, klient odpověď odmítne jako chybnou a nabídne opakování, místo aby ukázal rozporné počty. Při aktivním filtru stavu či termínu se obě skupiny počítají s odlišným průřezem a tato rovnost se nevyžaduje; `facets: null` znamená nedostupné počty, nikoli nuly. Izolovaný regresní test pokrývá rozpor a reálný D1 → API → desktop/mobilní Chromium ověřuje běžný případ a přístupnost. Nejde o úplné uzavření #400 ani potvrzení aktuálnosti zdrojů.

## Konzistence úplných počtů poskytovatelů — dílčí #400
Když není aktivní filtr poskytovatele a seznam poskytovatelů není zkrácený, součet jejich počtů musí odpovídat srovnatelné skupině: bez filtrů stavu/termínu celkovému počtu stavů, jen se stavem celkovému počtu termínů, jen s termínem celkovému počtu stavů. Při současném filtru stavu a termínu nebo filtru poskytovatele nejsou tyto skupiny srovnatelné. Zkrácený seznam je pouze dolní mez a nedostupné `facets: null` nejsou nuly. Rozpornou úspěšnou odpověď klient odmítne a nabídne opakování; nezobrazuje falešné počty.

## Definition of Done
Kód je otestovaný, CI zelené, docs aktualizované, failure mode bezpečný a UX nevytváří falešnou jistotu.
