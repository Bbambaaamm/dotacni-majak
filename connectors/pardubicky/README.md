# Pardubický kraj — Dotační portál connector

## Autoritativní zdroj
https://dotace.pardubickykraj.cz/grants

Veřejný portál poskytuje server-rendered katalog dotačních programů a veřejné detailní stránky s podmínkami.

## Identity
Detail URL používá stabilní UUID:
`/grants/<uuid>`

Source identity:
`PAK-<uuid>`

## Normalizovaná data
Connector získává:
- title
- application window
- native status
- supportedActivitiesText / cíl programu
- eligibleApplicantsText
- grantAmountMin/MaxMinor
- ownContributionText + první explicitní minimum v basis points
- application URL
- official artifacts
- region CZ053

## Safety
- RAW-first
- GuardedHttpClient
- disappearance != cancellation
- explicitní termín detailu má přednost před seznamovou kartou
- procenta a finance se ukládají deterministicky, bez float v databázi
- pokud různé skupiny žadatelů mají jinou spoluúčast, celý text se zachová; první obecné minimum není vydáváno za univerzální pravidlo pro všechny typy žadatelů
- přihlášení/odeslání žádosti se neautomatizuje

## Důležitý příklad
Program C1 2026 podporuje výstavbu, rekonstrukce a opravy sportovních zařízení. Je vhodným reálným regression příkladem pro záměry typu rekonstrukce tenisových kurtů.
