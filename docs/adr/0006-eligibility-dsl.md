# ADR-0006: Deterministic eligibility DSL

## Status
Accepted

## Decision

Eligibility podmínky se ukládají jako omezený strom:

```
EligibilityRuleSet
└── RuleGroup (AND / OR / NOT)
    ├── RuleGroup
    └── RuleCondition
```

RuleCondition odkazuje na registrovaný `AttributeDefinition` a používá pouze explicitně povolený operátor:

EQ, NEQ, IN, NOT_IN, LT, LTE, GT, GTE, BETWEEN, EXISTS, NOT_EXISTS,
CONTAINS, INTERSECTS, DATE_BEFORE, DATE_AFTER, GEO_WITHIN, GEO_NOT_WITHIN.

Žádný uložený JavaScript/Python, `eval()` nebo jiný arbitrary expression engine není povolen.

## UNKNOWN

Chybějící hodnota se nikdy automaticky nepřevádí na FAIL.

Povolené unknown policy:
- `PROPAGATE`
- `NOT_APPLICABLE`

Veřejný evaluator později mapuje stav do ELIGIBLE / LIKELY_ELIGIBLE /
NEEDS_INFORMATION / INELIGIBLE / NEEDS_REVIEW podle completeness a verification.

## Attribute Registry

Atributy jsou data, nikoliv hardcoded větve:
- `applicant.*`
- `project.*`

Často používané hodnoty mohou mít výkonné SQL sloupce/resolver, ale rules engine používá stabilní attribute key.

## Consequences
- nové typy podmínek lze přidat daty,
- pravidla jsou auditovatelná a testovatelná,
- typ/operator compatibility validuje runtime evaluator,
- každý kritický condition může odkazovat na `field_evidence`.
