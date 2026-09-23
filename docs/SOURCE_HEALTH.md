# Source Health & Scheduler Watchdog

Dotační maják veřejně nesmí působit, že „žádné nové dotace nejsou“, pokud ve skutečnosti pouze neběžel scheduler nebo se rozbil parser.

## Veřejné stavy
- **HEALTHY** — zdroj běží podle plánu a poslední data prošla quality gate.
- **DEGRADED** — data mohou být částečně zastaralá nebo poslední plánovaný běh chybí; zobrazujeme last-known-good.
- **UNAVAILABLE** — přímý healthcheck selhává, zdroj nikdy úspěšně neproběhl nebo je poslední úspěch příliš starý.

## Sledované časy
- last_expected_run_at
- last_actual_run_at
- last_success_at
- last_change_at
- last_checked_at

## Watchdog
Běh je missed, pokud po expected slotu + grace period neexistuje odpovídající actual run.

Source se stává UNAVAILABLE, pokud je last_success starší než konfigurovaný násobek expected interval.

## Quality integration
DEGRADED Data Quality Gate automaticky degraduje Source Health a blokuje destruktivní reconciliation.

## UX
Při problému zobrazit například:

> Zdroj je momentálně omezený. Poslední úspěšná kontrola: 22. 9. 2026 03:18. Níže zobrazujeme poslední ověřená data.

Nikdy neskrývat stáří dat a nikdy tvrdit „hlídáme všechny dotace“.
