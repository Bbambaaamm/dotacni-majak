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


## Anonymous resolve API

API Worker poskytuje read-only resolver:

`GET /share/<capability-token>`

Resolver:
- validuje tvar tokenu před D1 query,
- používá stejný domain-separated SHA-256 hash jako sharing domain model,
- akceptuje pouze aktivní scope `PROJECT_READ_ONLY`,
- revokovaný, expirovaný, neznámý i malformed token vrací navenek jako stejné `404 SHARE_NOT_FOUND`,
- vrací pouze explicitní safe projection: id, title, intent, currency, budget, planned dates, updatedAt,
- nikdy nevrací owner_user_id, applicant_profile_id, interní poznámky, documents/storage refs ani account/watch data.

Response má:
- `Cache-Control: private, no-store`,
- `X-Robots-Tag: noindex, nofollow`,
- `Referrer-Policy: no-referrer`.

## Zbývající blocker Issue #55

Anonymous read path je bezpečně implementovaný. Owner mutation path (create/revoke share)
zůstává záměrně neexponovaný, dokud projekt nemá skutečný server-side authentication
model. Klientský `owner_user_id` parametr není akceptovatelná authorization náhrada.
