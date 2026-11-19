# Privacy Architecture

## Princip
Sbírat pouze data nezbytná pro nalezení, vyhodnocení a sledování dotace. Dotační maják není CRM ani datový broker.

## Data classes
### Veřejná dotační data
Výzvy, poskytovatelé, dokumenty a provenance.

### Applicant profile
U organizací preferovat veřejné registry. U fyzických osob minimalizovat osobní údaje a nikdy automaticky nedoplňovat citlivé atributy.

Profil je volitelně ukládán lokálně (local-first) bez registrace přes stránku `/profil`. Na zařízení uživatele se ukládají pouze údaje, které uživatel výslovně zadal nebo importoval; aplikace sama nespouští ARES/ČSÚ ani nedoplňuje osobní identifikační údaje (rodné číslo, kontakt, e-mail). Místní údaje nejsou automaticky odesílány na server a samy o sobě neznamenají rozhodnutí o způsobilosti.

Profil má `schemaVersion` a provenance po poli (uživatelem uvedeno, automaticky získáno z oficiálního zdroje, potřeba ověřit). UI umožňuje uložit typ žadatele, kód obce a počet obyvatel, zobrazit export JSON, importovat platný JSON a profil výslovně smazat. Neznámá verze či neplatný záznam se nepoužije ani automaticky nevymaže; před novým uložením musí uživatel rozhodnout o smazání. Selhání úložiště není zaměněno za prázdný profil. Budoucí serverová synchronizace vyžaduje samostatný opt-in a správně ověřenou identitu; není součástí této stránky.

### Project data
Záměr, rozpočet, lokalita, readiness a eligibility odpovědi jsou private-by-default.

### Authentication/contact
Pouze pro synchronizaci/watch/notification. První search funguje bez registrace.

## Zakázané výchozí chování
- neukládat citlivá data pro jistotu
- nepoužívat projekt pro reklamu
- neposílat projekt třetím AI providerům bez jasného účelu
- žádný veřejný share bez explicitní akce
- žádný session replay zachycující projektový text

## Retention
Před beta definovat retention pro auth/security logs, notifications, anonymous telemetry a backups. Uživatel má mít export/deletion pro serverově uložené projekty/profil.

## Analytics
Preferovat agregované metriky: search success/no-result, relevance feedback, source health, latency/error rate. Natural-language project text není běžná analytics dimension.

## AI
Minimalizovat payload, neposílat nepotřebné identifikátory, dokumentovat provider retention/training policy a zachovat deterministic fallback core funkcí.

## Share
Read-only share je opt-in a revocable, s noindex. Nesmí implicitně odhalit applicant profile mimo nezbytný sdílený přehled.

## Transparency
Veřejná privacy stránka před beta popíše data, účel, retention, třetí strany, export/deletion a privacy kontakt.
