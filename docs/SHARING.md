# Read-only project sharing

Issue: #55

## Bezpečnostní model

Share link je explicitní read-only capability:

`/s/<token>`

Raw share token se vrátí vlastníkovi při vytvoření odkazu. Server ukládá pouze
domain-separated SHA-256 hash.

V1 podporuje pouze scope:

`PROJECT_READ_ONLY`

Share nikdy neuděluje editaci, upload, změnu watch ani přístup k účtu.

## Anonymní vlastnictví projektu

MVP nevyžaduje placeného identity providera. Anonymně vytvořený projekt dostane
samostatný owner capability token s minimálně 256 bity entropie.

- raw owner token server vrátí pouze při vydání/rotaci,
- persistentně je uložen pouze jeho domain-separated hash,
- owner token je project-scoped,
- owner token a share token používají rozdílné hash domains,
- token lze rotovat/revokovat,
- klientský `owner_user_id` není authorization mechanismus.

Frontend ukládá aktivní owner capability pouze do `sessionStorage` pro obnovu
stránky v rámci relace, nikoli do permanentního `localStorage`. Uživatel je
upozorněn, že ztracený anonymní owner key nelze bez budoucího account bindingu
obnovit.

## Mutation API

- `POST /projects` → projekt + owner capability
- `POST /projects/:id/shares` → nový read-only share, Bearer owner capability
- `DELETE /projects/:id/shares/:shareId` → idempotentní revokace
- `POST /projects/:id/owner/rotate`
- `DELETE /projects/:id/owner/revoke`

Vstup je bounded, owner authorization je server-side a mutation flow chrání
proti project-scoped IDOR.

## Read API

`GET /share/<capability-token>`

Resolver:
- validuje tvar tokenu před D1 query,
- akceptuje jen aktivní `PROJECT_READ_ONLY`,
- revokovaný, expirovaný, neznámý i malformed token vrací shodně jako
  `404 SHARE_NOT_FOUND`,
- vrací pouze safe projection: id, title, intent, currency, budget,
  planned dates a updatedAt.

Nikdy nevrací owner identifier/capability, applicant profile, interní poznámky,
document storage refs, account ani watch data.

## Privacy/cache/indexing

API response:
- `Cache-Control: private, no-store`
- `X-Robots-Tag: noindex, nofollow`
- `Referrer-Policy: no-referrer`

Webová `/s/<token>` stránka nastavuje `robots=noindex,nofollow` a
`referrer=no-referrer` také na klientu. Produkční edge/static routing má
později doplnit HTTP `X-Robots-Tag` pro `/s/*`, protože client-side meta není
sama o sobě plnohodnotná serverová indexační kontrola.

## Revokace a expirace

- default TTL: 30 dní,
- maximum: 365 dní,
- revokace je okamžitá,
- neznámý a zrušený odkaz se navenek nerozlišuje.

## Audit

Auditují se create/resolve/revoke/denial události. Raw owner/share token se
nikdy neloguje.

## UI

`/projekty` umožňuje vytvořit anonymní projekt, zobrazí owner key s jasným
bezpečnostním upozorněním a vytvořit/revokovat read-only odkaz.

`/s/<token>` je skutečně read-only a zobrazuje jen safe projection.

Dotační maják na sdílené stránce výslovně uvádí, že nejde o oficiální
rozhodnutí poskytovatele.
