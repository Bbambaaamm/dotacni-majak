# Finance Engine

Finance je oddělená od relevance i eligibility.

## Základní pravidlo
„90% dotace“ neznamená automaticky „10 % vlastních peněz“.

Engine rozlišuje:
- způsobilé náklady,
- nezpůsobilé náklady,
- nerefundovatelnou DPH,
- maximální míru podpory,
- min/max grant,
- min/max velikost projektu,
- payment mode a předfinancování.

## Reprezentace
- peníze = integer minor units,
- procenta = basis points.

Žádný floating point pro kritické finance.

## Výstup
- max_grant_minor,
- own_eligible_contribution_minor,
- ineligible_costs_minor,
- nonrecoverable_vat_minor,
- **minimum_real_cash_requirement_minor**,
- minimum_prefinancing_requirement_minor, pokud lze bezpečně určit.

## UNKNOWN / incomplete
Chybějící údaj nikdy není nula.

Pokud chybí například:
- eligible costs,
- ineligible costs,
- nonrecoverable VAT,
- total project cost,
- support_rate_max,

výsledek je **NEEDS_INFORMATION** a částky, které by vyžadovaly domněnku, jsou null.

## Scenario selection
Finance engine sám nevybírá „nejlepší“ variantu.

- přesně jeden PASS scenario → lze vyhodnotit,
- více PASS scenarios → NEEDS_INFORMATION / explicitní volba nebo další pravidlo,
- pouze UNKNOWN → NEEDS_INFORMATION,
- samé FAIL → SCENARIO_NOT_APPLICABLE.

## Příklad
Projekt:
- celkem 4 000 000 Kč,
- eligible 3 500 000 Kč,
- ineligible 400 000 Kč,
- nonrecoverable VAT 100 000 Kč,
- max support 90 %.

Max grant = 3 150 000 Kč.

Own eligible contribution = 350 000 Kč.

Minimum real cash requirement = 350 000 + 400 000 + 100 000 = **850 000 Kč**.

To je číslo, které má UI upřednostnit před samotným „90 %“.
