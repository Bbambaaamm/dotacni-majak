# Project owner capability API

Issues: #203, #55

Dotační maják může v zero-cost MVP vytvořit anonymní projekt bez externího
identity providera. Vlastnictví je reprezentováno samostatným high-entropy
owner capability tokenem.

## Create project

`POST /projects`

JSON:
```json
{
  "title": "Rekonstrukce tenisových kurtů",
  "naturalLanguageIntent": "Chceme zrekonstruovat tři tenisové kurty.",
  "currencyCode": "CZK",
  "estimatedTotalBudgetMinor": 400000000
}
```

Response `201` obsahuje `projectId` a `ownerCapability`.

Owner capability je zobrazena pouze v této odpovědi. Server persistuje pouze
domain-separated SHA-256 hash.

Projekt + owner capability + audit vznikají přes D1 `batch()`, aby šlo o jednu
transakční sekvenci.

## Create read-only share

`POST /projects/<projectId>/shares`

Header:
`Authorization: Bearer <ownerCapability>`

Volitelné JSON:
```json
{ "expiresInDays": 30 }
```

Response vrací pouze nový read-only share token. Owner capability není share
token a jednotlivé token domains jsou kryptograficky oddělené.

## Resolve share

`GET /share/<shareToken>`

Vrací pouze explicitně whitelisted public projection projektu a používá:
- `Cache-Control: private, no-store`
- `X-Robots-Tag: noindex, nofollow`
- `Referrer-Policy: no-referrer`

## Revoke share

`DELETE /projects/<projectId>/shares/<shareId>`

Vyžaduje owner capability. Response je záměrně idempotentní a non-disclosing
(`204`) i pro již zrušený/neexistující share.

## Rotate owner capability

`POST /projects/<projectId>/owner/rotate`

Vyžaduje aktuální owner capability a vrací nový raw token. Starý hash je atomicky
nahrazen.

## Revoke owner capability

`DELETE /projects/<projectId>/owner/revoke`

Po revokaci nelze anonymní projekt spravovat, dokud nebude existovat budoucí
account-binding/recovery flow.

## Security invariants

- Authorization nikdy nevychází z `owner_user_id` poslaného klientem.
- Raw owner/share tokeny se nepersistují.
- Request body je omezen na 16 KiB.
- Owner token projektu A nemůže spravovat projekt B.
- Unknown/invalid share resolver neodhaluje existenci projektu.
- Share public projection neobsahuje applicant profile, owner principal, interní
  poznámky, dokumentové storage refs ani account/watch data.
