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

## Rolling baseline

Při každém úspěšném source runu se pro daný zdroj počítá **rolling baseline** — median počtu záznamů a průměrné HTTP error/success, parse/validate rate přes posledních N dokončených běhů té **téže adapterové verze**. Baseline se ukládá trvale (jedna řádka na zdroj) a nepoužívá se k tréninku žádného modelu — pouze jako vstup pro deterministický rule-based quality gate.

- **Rolling window / median** — posledních `window_size` dokončených běhů definuje baseline (`source_run_baselines.median_records`, `mean_error_rate`, `mean_success_rate`).
- **Bootstrap / UNKNOWN stav** — pokud existuje méně než `min_samples` běhů téže verze, všechny signální pole jsou NULL (`is_bootstrapped = 1`). Kvalita gate pak zachází s tím jako s „nemám základnu" — ne jako „zdroj nefunguje". Žádný první běh ani změna verze se tak nedostane do DEGRADED kvůli absence historie.
- **Zdrojová resetace verze** — běhů z jiné `adapter_version` se v výpočtu baseline nepoužívají. Upgrade parseru/connectoru tedy resetuje baseline okno namísto srovnávání nekompatibilních počtů. Po změně verze zůstává baseline v bezpečném UNKNOWN stavu, dokud není získáno dostatečné množství nových běhů té nové verze.
- **Trvalost / D1** — `source_run_baselines` je nová persistentní tabulka; `source_runs` je už existující auditní log pro běhů ingestions (LOCKED / neukončené běhy se při počítání baseline ignorují).

## UX
Při problému zobrazit například:

> Zdroj je momentálně omezený. Poslední úspěšná kontrola: 22. 9. 2026 03:18. Níže zobrazujeme poslední ověřená data.

Nikdy neskrývat stáří dat a nikdy tvrdit „hlídáme všechny dotace“.
