# Document Security

Externí PDF/DOCX/XLSX/XML jsou **nedůvěryhodný vstup**.

## Povinný tok
RAW snapshot → security inspection → parser → extraction.

Parser nikdy nesmí dostat dokument, který neprošel security inspection.

## Limity
Výchozí policy:
- max soubor 50 MiB,
- max 5 000 ZIP entries,
- max 200 MiB celkem po rozbalení,
- max 50 MiB jedna položka,
- max kompresní poměr 150×.

Limity jsou konfigurovatelné podle zdroje pouze reviewovanou změnou.

## OpenXML
DOCX/XLSX jsou ZIP kontejnery. Kontrolujeme:
- signaturu ZIP,
- počet položek,
- celkovou rozbalenou velikost,
- velikost položky,
- kompresní poměr,
- path traversal,
- šifrované entry,
- očekávanou OpenXML strukturu,
- XML DTD/ENTITY.

## XXE
XML s `DOCTYPE` nebo `ENTITY` je odmítnuto před downstream parserem.

## Embedded links
Parser může odkazy pouze extrahovat jako data. Nesmí je sám stahovat.
Jakýkoli následný fetch jde znovu přes GuardedHttpClient a jeho allowlist/SSRF kontroly.

## OCR
OCR není první volba. Je fallback pouze pro PDF bez použitelné textové vrstvy a musí běžet izolovaně s vlastními resource limity.

## MIME
Deklarovaný MIME musí odpovídat základní signatuře/struktuře. Neočekávané typy se nedohadují a nekonvertují automaticky.
