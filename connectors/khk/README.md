# Královéhradecký kraj connector

Issue: #69

## Ověřený veřejný kontrakt
- portal: https://dotace.khk.cz/
- discovery: POST `/api/Data/GetProjectSubprojectCollection`
- detail: POST `/api/Data/GetSubproject`
- document metadata: POST `/api/Data/GetSubprojectDocumentCollection`

API origin:
`https://dotisreactfunctions.azurewebsites.net`

## RAW-first
Každá discovery/detail/document-metadata response je uložená jako immutable RAW snapshot.

## Identita
`id_Def_Subproject` je stabilní source identity; veřejný program code (`memo`) je zachovaný v raw fields a detail URL.

## Finance
Veřejné fields `priceMinimum`, `priceMaximum`, `totalPrice` a `percentMaximum` se normalizují pouze tehdy, pokud příslušný `*Web` flag je true. Zdrojová hodnota zůstává zachována.

## Status
Native numeric `state` se neinterpretuje bez doloženého slovníku. Uživatelský normalized status se konzervativně odvozuje z explicitních dateBeg/dateEnd.

## Documents
v0.1 načítá veřejný seznam dokumentů a jejich metadata. Binární download je záměrně vypnutý, dokud samostatný research nezachytí skutečný veřejný download contract; URL se z ID neodhaduje.
