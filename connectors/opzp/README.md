# OPŽP 2021–2027 connector

Oficiální zdroj: Operační program Životní prostředí.

- Listing: https://opzp.cz/nabidka-dotaci
- Detail: https://opzp.cz/dotace/<číslo>-vyzva/
- Retrieval: veřejné HTML + veřejné dokumenty.
- Autorita: oficiální.
- Refresh pro MVP: 4 h.
- RAW-first: listing, detail i stažené dokumenty se snapshotují.

## Scope

Tento adapter pokrývá **OPŽP 2021–2027**. Modernizační fond na webu SFŽP
má odlišnou strukturu a má samostatný connector issue, aby změna jednoho webu
nepoškodila druhý.

## Identity

External ID: `OPZP-<číslo výzvy>`.

Canonical status se mapuje pouze z explicitního textu webu nebo jako
konzervativní fallback z termínu. Zmizení z listingu nikdy samo o sobě
neznamená CLOSED/CANCELLED.

## Data z detailu

- title
- source/native status
- druh výzvy
- termín podání
- alokace
- popis
- příjemci podpory
- veřejné dokumenty/přílohy

## Coverage caveat

Listing obsahuje server-rendered aktuální/plánované výzvy. Pokud web později
přesune část výsledků pouze za dynamické „Načíst další“, live smoke a Source
Health musí takovou strukturální změnu detekovat; adapter nesmí domýšlet
nezdokumentovaný AJAX endpoint.
