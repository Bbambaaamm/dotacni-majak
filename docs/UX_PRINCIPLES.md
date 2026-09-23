# UX Principles & Audit

## North Star
Každá důležitá stránka musí odpovědět:
# Co mám udělat teď?

## P0 — před public beta

### Falešná jistota
Rozlišovat:
- ověřeno,
- pravděpodobné,
- chybí informace,
- neověřeno.

### Relevance ≠ eligibility
„Velmi dobrá shoda“ nesmí vypadat jako „šance získat dotaci“.

### Finance
Zobrazovat nejen support rate, ale skutečnou vlastní potřebu a případné předfinancování.

### Žádné slepé uličky
- 0 výsledků → Project Watch
- INELIGIBLE → konkrétní důvod + podobné možnosti
- UNKNOWN → doplnit údaj
- source down → poslední ověřená data + stav zdroje
- closed → podobné / další kolo

### Signup
První search a detail bez registrace.

### Chyby
Lidský text, ne interní error názvy.

## P1

### „Dotáhne“ musí být skutečná funkce
Každý detail/workspace má Next Action komponentu.

### Progressive profiling
Otázky řadit podle očekávané informační hodnoty, ne pevného formuláře.

### Comparison
Faktické atributy bez automatického vítěze.

### Administrativní náročnost
Nevymýšlet subjektivní score. Zobrazit měřitelná data: počet příloh, blockers, unknowns.

### Deadline
Absolutní datum + zbývající čas + nedokončené blockers.

### Historie
Historické projekty vizuálně oddělit.

### Source Coverage
Transparentnost je feature, ne interní dashboard.

## Accessibility UX
- ikona nikdy bez textového významu,
- focus výraznější než hover,
- tooltip není místo pro kritické informace,
- finance chart má textový ekvivalent,
- 200% zoom/reflow.

## Mobile
- filtry jako accessible dialog/sheet,
- jedna hlavní sticky action,
- comparison atribut po atributu,
- detail přes progressive disclosure.

## Produktové příležitosti P2
- read-only share,
- PDF export,
- notes,
- public changelog,
- source suggestion.

## Observability UX
Při rozbitém zdroji:
> Zdroj je momentálně nedostupný. Poslední úspěšná kontrola: … Níže zobrazujeme poslední ověřená data.

## Co odstranit
- příliš textu na homepage,
- ručně psaný font pro funkční text,
- dominantní lighthouse photo v pracovní části,
- chatbot-first UX.

## Pět povinných beta toků
1. intent → results → detail → source
2. intent → no result → Project Watch
3. result → UNKNOWN → question → reevaluation
4. result → Chci tuto dotaci → workspace → next action
5. saved project → changed call → notification → concrete diff

## User research
Testovat úkoly, ne názory na vzhled:
- najděte podporu,
- zjistěte proč nevyhovuje,
- uložte sledování,
- zjistěte next action,
- najděte oficiální zdroj.
