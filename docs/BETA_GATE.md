# Public Beta release gate

Issue: #40

## Co je automatizovatelné

CI může ověřit:
- unit/integration/API/web testy,
- build,
- accessibility smoke test,
- schema/ontology/data contract validaci,
- anonymizovanou strukturu usability evidence,
- že nejsou otevřená P0/P1 zjištění uvedená v evidence file.

Automatizace ale **nesmí předstírat skutečný usability research**.

## Povinný lidský důkaz

Před uzavřením #40 musí být v privátně/anonymizované research evidenci skutečné
testování minimálně těchto segmentů:

- obec/město,
- spolek/neziskovka,
- občan,
- malá firma/OSVČ,
- škola/příspěvková organizace.

Repo neukládá jména, e-maily, nahrávky ani jiné zbytečné osobní údaje.

Každý z úkolů A–F z `docs/BETA_RESEARCH_PLAN.md` musí mít skutečný observační
záznam. Issue #40 nelze uzavřít pouze syntetickým/persona testem.

## Findings

Každé zjištění má anonymní ID, severity a stav:

- P0 — může vést k závažně chybnému rozhodnutí / bezpečnostnímu dopadu,
- P1 — významně brání dokončení nebo pochopení kritického toku,
- P2 — střední UX problém,
- P3 — drobnost.

Beta je blokovaná při:
- OPEN P0/P1,
- RETEST_REQUIRED P0/P1,
- chybějícím segmentu,
- chybějícím úkolu A–F,
- chybějícím explicitním lidském GO rozhodnutí.

## Evidence workflow

1. Zkopírovat `research/beta-sessions.example.json` jako
   `research/beta-sessions.json`.
2. Po každé relaci zapsat pouze anonymizované výsledky.
3. Zjištění opravit přes samostatná GitHub issues/PR.
4. P0/P1 po opravě znovu otestovat a označit VERIFIED.
5. Reviewer nastaví decision.status=GO + datum + stručné odůvodnění.
6. Spustit manuální GitHub Action **Public Beta Gate**.

## Lokální validace

```bash
python3 scripts/validate_beta_research.py research/beta-sessions.json
python3 scripts/validate_beta_research.py --require-gate research/beta-sessions.json
```

První příkaz ověří strukturu. Druhý je release gate a bez skutečné human evidence
má správně selhat.
