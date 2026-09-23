# ADR-0005: Licence a governance model

## Status
Accepted

## Context

Dotační maják je veřejně prospěšný open-source projekt určený občanům, obcím,
spolkům, firmám a dalším organizacím. Chceme co nejnižší bariéru pro:
- veřejnou správu,
- neziskové organizace,
- univerzity,
- komerční dodavatele pracující pro veřejný sektor,
- jednotlivé přispěvatele.

Současně potřebujeme jednoduchý model, který je srozumitelný i malému projektu
bez právního/administrativního aparátu.

## Zvažované varianty

### MIT
Výhody:
- velmi jednoduchá a široce kompatibilní,
- minimální bariéra adopce,
- snadno použitelná v municipalitách i komerčních integracích,
- nízká administrativní režie.

Nevýhoda:
- nevyžaduje zveřejnění změn nebo síťově provozovaných forků.

### Apache-2.0
Výhody:
- permissive,
- explicitní patentové ustanovení.

Nevýhody:
- delší a administrativně složitější než MIT,
- pro současný malý projekt nepřináší dostatečný praktický přínos navíc.

### AGPL-3.0
Výhoda:
- silně chrání otevřenost i při poskytování služby přes síť.

Nevýhody:
- může komplikovat nasazení v organizacích a u dodavatelů,
- snižuje ochotu integrovat projekt do existujících řešení.

### EUPL-1.2
Výhody:
- evropský veřejnosektorový kontext,
- copyleft.

Nevýhody:
- menší všeobecná známost v komunitě,
- vyšší právní friction pro globální/open-source integrace.

## Decision

Používáme **MIT License** pro zdrojový kód a dokumentaci tohoto repozitáře.

Důvodem je maximalizace praktického veřejného užitku a možnosti reuse.
Veřejnou misi nebudeme vynucovat složitým copyleftem, ale:
- transparentní governance,
- provenance-first architekturou,
- veřejným issue/PR workflow,
- open-source-first produktem,
- jasnou komunikací Source Coverage.

Název a vizuální identita „Dotační maják“ nesmí být používány tak, aby třetí
strana vytvářela dojem oficiálního provozovatele nebo endorsementu původního
projektu. Licence ke kódu sama o sobě nepředstavuje takové doporučení.

## Contribution model

- Bez CLA v první fázi.
- Přispěvatel musí mít právo příspěvek poskytnout.
- Odesláním PR souhlasí, že přijatý příspěvek bude distribuován pod MIT.
- Kritické změny canonical contracts vyžadují ADR/review.
- Connector příspěvek musí mít oficiální source provenance a fixture tests.
- Security incidenty nejdou do veřejného issue před koordinovaným řešením.

## Governance

Model je **maintainer-led**:
- běžné změny: issue → branch → PR → CI → review → merge,
- architecture/schema/security invariants: ADR + review,
- breaking canonical změny: migration/compatibility plan,
- release gate: security, privacy, accessibility a data-quality kontrola.

## Consequences

Pozitivní:
- nízká bariéra reuse,
- snadné přispívání,
- jasná licence od rané fáze.

Trade-off:
- třetí strana může vytvořit proprietární fork. Tento trade-off akceptujeme
  ve prospěch širšího nasazení a veřejného užitku.
