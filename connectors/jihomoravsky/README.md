# Jihomoravský kraj — dotační portál connector

## Oficiální zdroje
- Dotační oblasti: https://dotace.kr-jihomoravsky.cz/Oblasti.aspx
- oblastní seznamy `/Folders/...aspx`
- detail programu `/Grants/<id>-...aspx`

## Detail
Veřejné stránky publikují alokaci, účel, příjem žádostí, územní lokalizaci a u řady titulů také příjemce, minimální/maximální podporu a spoluúčast.

Connector nepoužívá „Stav Vaší žádosti“, Portál obcí ani žádné přihlášené rozhraní.

## Safety
- RAW-first
- stabilní source identity = číselné ID v `/Grants/<id>-...`
- disappearance != cancellation
- částky = integer minor units
- spoluúčast = basis points pouze pokud je číselně jednoznačná
- nečíselné „viz příloha“ zůstává UNKNOWN

Region: CZ064.
