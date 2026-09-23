# Finance model

## Zásada
Dotační maják nesmí zaměňovat různé formy veřejné podpory.

Canonical `FundingInstrumentType`:
- `GRANT` — nevratná dotace/příspěvek,
- `LOAN` — úvěr, včetně zvýhodněného nebo bezúročného,
- `GUARANTEE` — záruka/ručení za financování,
- `EQUITY` — kapitálový nástroj,
- `MIXED` — kombinace více forem,
- `OTHER` — jiný veřejný finanční nástroj.

## Grantový finance engine
Současný deterministický engine počítá pouze `GRANT`.

Pro ostatní typy vrací:
`INSTRUMENT_NOT_SUPPORTED`

a nikdy neinterpretuje např. „70% záruka“ jako „70% dotace“.

Specializované kalkulátory pro úvěry/záruky mohou být přidány později, ale musí mít vlastní model:
- jistina,
- úrok,
- splatnost,
- odklad,
- odpuštění části jistiny,
- výše záruky,
- zaručovaný úvěr,
- poplatky,
- cash-flow.

## Backward compatibility
Stávající grantové scénáře mají default `GRANT`. Nové negrantové zdroje musí instrument type nastavit explicitně.
