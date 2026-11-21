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
Retention pro auth/security logs, notifications, anonymous telemetry, backups a
uživatelská data je definována v `docs/PRIVACY_DATA_INVENTORY.md` a
verifikována automaticky v `tests/python/test_privacy_data_inventory.py`.
Navrhované hodnoty jsou označeny `proposed_pre_beta` a vyžadují schválení na
Privacy gate před Public Beta (#40). Shrnutí:

- **Security/audit logy** (`project_owner_audit_events`, `share_audit_events`): 1 rok.
- **Operační logy** (`outbox_events`, `source_runs`, `source_records`,
  `ingestion_runs`, `change_events`, `scheduler_watchdog_events`, `source_health`): 90 dní.
- **Notifications**: 90 dnich ode dní vytvoření.
- **Push endpointy** (šifrované): do unsubscription/revoke, poté 30 dnů.
- **Uživatelská data** (profiles, projects, watches, uploads): do uživatelského
  požadavku na smazání; export i deletejs jsou owner-scoped.
- **Capability/share hash**: s projektem; share link expiruje (default 30d, max 365d);
  zrušené/expirované hashe se sběhem 30 dnů vymažou.
- **Backups**: retention sjednaný v rámci v1.0 gate (#41).
- **Analytics**: NOT IMPLEMENTED — `send_metrics: false`; žádná implicitní sběrnost.


## Analytics
Preferovat agregované metriky: search success/no-result, relevance feedback, source health, latency/error rate. Natural-language project text není běžná analytics dimension.

## AI
Minimalizovat payload, neposílat nepotřebné identifikátory, dokumentovat provider retention/training policy a zachovat deterministic fallback core funkcí.

## Share
Read-only share je opt-in a revocable, s noindex. Nesmí implicitně odhalit applicant profile mimo nezbytný sdílený přehled.

## Transparency
Veřejná privacy stránka před beta popíše data, účel, retention, třetí strany, export/deletion a privacy kontakt.
