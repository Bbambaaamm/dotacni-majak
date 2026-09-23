# Ministerstvo kultury connector

Oficiální Source Adapter pro jednotlivé dotační výzvy Ministerstva kultury.

## Discovery
Stabilní centrální rozcestník:
https://www.mk.gov.cz/granty-a-dotace-cs-1234

Connector může následovat omezený počet oficiálních indexových/ročních vyhlašovacích stránek, ale jako GrantCall publikuje pouze odkazy, které lze identifikovat jako jednu konkrétní výzvu.

Výsledky, vyúčtování, zápisy komisí a archivy nejsou aktivní GrantCall.

## Extrakce
- číslo výzvy, pokud existuje,
- deadline,
- účel/zaměření,
- oprávnění žadatelé,
- způsob podání,
- PDF/DOCX/XLSX/XLSM dokumenty.

## Coverage
Coverage je záměrně částečné a transparentní. Agregované roční stránky s více programy slouží pro discovery; pokud jednotlivé výzvy existují pouze uvnitř komplexního dokumentu, vyžadují samostatnou document-extraction implementaci.

Přihlášený Dotační portál MK se nescrapuje.
