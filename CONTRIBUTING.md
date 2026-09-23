# Přispívání do Dotačního majáku

Děkujeme za pomoc s veřejně prospěšným open-source projektem.

## Než začnete

Přečtěte:
1. `README.md`
2. `ARCHITECTURE.md`
3. `docs/AGENT_HANDOFF.md`
4. relevantní ADR a issue.

## Workflow

1. Najděte nebo založte konkrétní issue.
2. Vytvořte malou, scoped branch.
3. Přidejte implementaci + testy + dokumentaci.
4. Otevřete PR a propojte jej s issue.
5. Nechte proběhnout CI.
6. Reagujte na review bez obcházení bezpečnostních/data-quality pravidel.

## Connector contribution

Nový zdroj musí mít:
- oficiální URL a popsanou retrieval metodu,
- SourceDescriptor,
- explicitní coverage,
- RAW-first chování,
- fixtures,
- contract/unit testy,
- healthcheck,
- bezpečné disappearance chování,
- oddělený live smoke, pokud je rozumně možný.

Nevymýšlejte API a neobcházejte login, CAPTCHA ani technické ochrany.

## Canonical schema

Canonical schema neměňte pouze proto, aby vyhovoval jednomu connectoru.
Potřebná změna musí být obecná, zdokumentovaná a reviewovaná.

## Security

Bezpečnostní chyby neposílejte do veřejného issue s návodem k exploitu.
Postupujte podle `SECURITY.md`.

## Licence příspěvků

Odesláním příspěvku potvrzujete, že máte právo jej poskytnout a že přijatý
příspěvek může být distribuován pod MIT License projektu.

CLA v současné fázi nepoužíváme.
