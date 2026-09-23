# Read-only project sharing

Issue: #55

## Bezpečnostní model

Share link je explicitní, read-only capability. URL obsahuje pouze náhodný token s vysokou entropií:

`/s/<token>`

Raw token se po vytvoření vrátí vlastníkovi pouze jednou. Server ukládá pouze domain-separated SHA-256 hash.

## Vlastnictví

Projekt musí mít `owner_user_id`. Create/revoke operace musí provést server-side kontrolu vlastníka; klientský route guard nestačí.

## Scope

V1 podporuje jediný scope:

`PROJECT_READ_ONLY`

Share link nikdy neuděluje editaci, upload, změnu watch ani přístup k auth/account datům.

## Revokace a expirace

- default TTL: 30 dní,
- maximum: 365 dní,
- revokace je okamžitá,
- po revokaci/expiraci resolver nevrací project_id,
- neznámý token a neexistující projekt se navenek nerozlišují.

## Privacy

Share endpoint smí později vracet pouze explicitně whitelisted public projection projektu. Applicant profile, kontaktní údaje, dokumentové storage refs a interní poznámky nejsou implicitně součástí share payloadu.

Veřejná stránka musí mít `noindex, nofollow` a `Cache-Control: private, no-store`.

## Audit

Auditují se CREATED / RESOLVED / REVOKED a denial events. Raw token se nikdy neloguje.

## API/UI integration

Současná implementace záměrně nedává „Sdílet“ tlačítko do placeholder stránky Moje projekty. Owner mutation endpoint se připojí až s reálnou autentizací/project API. Anonymous resolve endpoint musí používat tento domain service a safe projection, ne číst projekt přímo podle tokenu.
