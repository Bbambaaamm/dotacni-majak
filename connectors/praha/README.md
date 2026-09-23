# Hlavní město Praha connector

## Autoritativní zdroj
Oficiální elektronická úřední deska MHMP — kategorie **Granty**.

Discovery používá oficiální RSS feed:
`https://eud.praha.eu/pub/rss/6000004/4/?...&kategorie_id=24&...&rss=True...`

## Proč RSS
RSS je veřejné, strojově čitelné a stabilnější než scraping celé listing stránky. Detail a přílohy se nadále stahují z oficiálních pražských domén.

## Safety / semantics
- RAW-first
- GuardedHttpClient
- RSS parser odmítá DTD/ENTITY declarations
- kategorie Granty obsahuje i administrativní/informační záznamy; discovery proto používá konzervativní title filter
- **datum sejmutí/vyvěšení z úřední desky není application deadline**
- submissionOpenAt/submissionCloseAt se vyplní jen při explicitním textu v detailu
- zmizení z RSS není CLOSED/CANCELLED

## Coverage
RSS feed může obsahovat omezený počet posledních záznamů. Source Health musí sledovat record count a případnou změnu RSS struktury. Starší/archivní programy lze později doplnit přes page-by-page notice-board discovery nebo Grantový portál, ale bez reverse-engineeringu neveřejných endpointů.
