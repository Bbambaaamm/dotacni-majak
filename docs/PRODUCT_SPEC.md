# Product Specification — Dotační maják

## Identita
**Dotační maják — Najde. Pohlídá. Dotáhne.**

Hlavní claim: **Vaše nápady. Více možností.**

Doplňující věta: **Od prvního nápadu přes vhodnou výzvu až po připravenou žádost.**

## Problém
Lidé často nevědí název programu ani úřední terminologii. Vědí jen, co chtějí uskutečnit.

Příklad:
> Chceme zrekonstruovat tenisové kurty.

Maják musí chápat význam:
- tenis → sportoviště → sportovní zařízení → sportovní infrastruktura,
- rekonstrukce → obnova → modernizace → technické zhodnocení → investice.

## Cílové skupiny
Občané, OSVČ, firmy, obce, města, kraje, spolky, sportovní kluby, neziskovky, školy, příspěvkové organizace, SVJ, družstva, zemědělci, výzkumné organizace a další relevantní žadatelé.

## Tři produktové sliby

### Najde
- natural-language intent,
- lexical + ontology + semantic retrieval,
- relevantní výzva nemusí obsahovat stejná slova jako dotaz.

### Pohlídá
- nové a plánované výzvy,
- termíny,
- nové dokumenty,
- změny podmínek,
- změny financování,
- pozastavení/uzavření/zrušení pouze na základě autoritativního důkazu.

### Dotáhne
- vysvětlí relevanci,
- deterministicky vyhodnotí známé podmínky,
- řekne, co chybí,
- spočítá finance,
- vytvoří checklist, timeline a workspace,
- řekne **Co máte udělat teď**.

„Dotáhne“ není garance schválení dotace.

## Klíčové oddělení výsledků
Nikdy neslučovat do jednoho skóre:
- **Relevance**
- **Eligibility**
- **Finance match**
- **Application readiness**

Nevytvářet „pravděpodobnost získání dotace“.

## Hlavní uživatelské toky

### Tok A — najdu vhodnou výzvu
Záměr → kandidáti → vysvětlení → doplnění informací → eligibility → finance → detail → workspace.

### Tok B — dnes nic vhodného není
Záměr → žádná otevřená možnost → **Pohlídat tento záměr** → nová výzva → reevaluace → notification.

### Tok C — něco nevíme
Výsledek → UNKNOWN → jedna důležitá otázka → přepočet.

### Tok D — výzva se změnila
Uložený projekt → nová GrantCallVersion → konkrétní diff → notification → aktualizovaný next action.

## Výsledková karta
Musí odpovědět:
1. Co je to?
2. Proč ji vidím?
3. Jsem známými podmínkami způsobilý?
4. Co ještě nevíme?
5. Co mě může vyřadit?
6. Kolik můžu získat?
7. Kolik skutečně potřebuju?
8. Do kdy?
9. Odkud informace pochází?
10. Co mám udělat teď?

## Finance
„90% dotace“ není totéž jako „10 % vlastních peněz“.

Rozlišovat:
- total cost,
- eligible cost,
- ineligible cost,
- support rate,
- max/min grant,
- own eligible contribution,
- non-recoverable VAT,
- pre-financing/cash-flow.

Primární výstup: **minimum_real_cash_requirement**.

## Provenance
U kritických údajů zobrazit:
- poskytovatel,
- dokument,
- stranu/sekci,
- datum kontroly,
- verification status.

UNKNOWN nikdy automaticky neznamená PASS ani FAIL.

## Project Watch
Plnohodnotná funkce, ne jen ikona zvonku.
Lze sledovat:
- výzvu,
- projekt,
- kategorii,
- poskytovatele,
- geografii,
- custom search.

## Application Workspace
Obsah:
- baseline GrantCallVersion,
- readiness,
- conditions,
- finance,
- requirements,
- attachments,
- tasks,
- deadlines,
- change timeline,
- notes,
- open questions.

## Porovnání
2–3 výzvy vedle sebe. Porovnávat fakta, ne vybírat automatického „vítěze“.

## Historická data
Samostatná doména. Pouze funkce „Podobné dříve podpořené projekty“. Nikdy je nezaměňovat za aktivní výzvy ani nepoužívat k falešné pravděpodobnosti schválení.

## MVP
- 4–6 kvalitních zdrojů,
- provenance,
- ontologie v1,
- hybrid search,
- applicant profile,
- eligibility,
- finance,
- detail + next action,
- Project Watch,
- change detection,
- Source Health,
- PWA,
- WCAG foundation,
- tenisový golden scenario.

## Beta
- širší CZ coverage,
- 14 krajů postupně,
- workspace,
- comparison,
- readiness,
- advanced finance,
- Web Push,
- PDF export,
- read-only share,
- relevance feedback,
- historical context,
- usability tests.

## v1.0
- široké CZ/EU coverage,
- production reliability,
- security/privacy/a11y gates,
- search-quality regression,
- bias/data-quality monitoring,
- recovery/runbook,
- governance/community,
- stabilní collaboration model.
