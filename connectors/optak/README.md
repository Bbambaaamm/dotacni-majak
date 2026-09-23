# OP TAK / API connector

Oficiální zdroj: Agentura pro podnikání a inovace.

- Listing: https://apiagentura.gov.cz/cs/radce/vsechny-vyzvy/
- Detail: veřejné stránky podporovaných aktivit / konkrétních výzev
- Retrieval: server-rendered HTML + veřejné dokumenty
- Autorita: OFFICIAL
- Refresh MVP: 4 h
- RAW-first: listing, detail i dokumenty

## Discovery
Oficiální listing přímo odděluje Otevřené a Uzavřené výzvy a zveřejňuje:
- datum vyhlášení,
- zahájení příjmu,
- ukončení příjmu,
- název/detail URL,
- zaměření aktivity.

## Detail
Adapter extrahuje:
- supported activities,
- eligible applicants,
- systém sběru,
- min/max projektové náklady,
- míru podpory,
- eligible costs,
- specifika/omezení,
- veřejné soubory.

## Safety
Status OPEN/CLOSED se přebírá z oficiální sekce listingu/detailu. Zmizení z listingu není automatický status transition.
