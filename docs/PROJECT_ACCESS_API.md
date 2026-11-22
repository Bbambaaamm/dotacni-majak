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

Povolená pole těla jsou `naturalLanguageIntent` (povinný neprázdný řetězec),
`title`, `currencyCode`, `estimatedTotalBudgetMinor`, `plannedStart` a
`plannedEnd`. Neznámé pole vrací HTTP 400 `UNKNOWN_PROJECT_FIELD`.
Vynechané nebo `null` volitelné hodnoty používají dosavadní výchozí hodnoty:
`title`, rozpočet a data jsou `null`, měna je `CZK`. Uvedené hodnoty musí mít
správný typ; neplatný `title`, `currencyCode`, `plannedStart` nebo `plannedEnd`
vrací HTTP 400 s kódem `INVALID_PROJECT_TITLE`, `INVALID_CURRENCY`,
`INVALID_PLANNED_START` nebo `INVALID_PLANNED_END`. Chybová odpověď obsahuje
pouze kód, nikoli vstupní hodnotu nebo text požadavku.

Owner capability je zobrazena pouze v této odpovědi. Server persistuje pouze
domain-separated SHA-256 hash.

Projekt + owner capability + audit vznikají přes D1 `batch()`, aby šlo o jednu
transakční sekvenci. Cloudflare dokumentuje batched statements jako SQL
transaction s rollbackem celé sekvence při chybě:
https://developers.cloudflare.com/d1/worker-api/d1-database/#batch

## Update project watch

`PATCH /projects/<projectId>/watch` vyžaduje owner capability a JSON objekt
s jediným povoleným polem `enabled` typu boolean (`true` nebo `false`).
Neznámé top-level pole vrací HTTP 400 `UNKNOWN_WATCH_FIELD`; chybějící nebo
neplatné `enabled` vrací HTTP 400 `INVALID_WATCH_ENABLED`.

## Create read-only share

`POST /projects/<projectId>/shares`

Header:
`Authorization: Bearer <ownerCapability>`

Volitelné JSON:
```json
{ "expiresInDays": 30 }
```

Skutečně vynechané tělo nebo `{}` používá 30 dní. Dodané JSON `null`, prázdné
tělo nebo tělo obsahující pouze bílé znaky vrací HTTP 400 `INVALID_SHARE_OPTIONS`.
Uvedené `expiresInDays` musí být bezpečné celé číslo 1–365; jeho explicitní
`null` i jiná neplatná hodnota vrací HTTP 400 `INVALID_SHARE_EXPIRY`. Neznámé
top-level pole vrací HTTP 400 `UNKNOWN_SHARE_FIELD`.

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
- Body limity jsou definované v `apps/api/src/bodyPolicy.ts` podle endpointu:
  `POST /projects`, `PUT`/`POST /applicant-profile` a
  `POST /projects/<projectId>/shares` používají výchozích 16 KiB;
  `PATCH /projects/<projectId>/watch` a `POST /projects/<projectId>/workspaces`
  i `PATCH /projects/<projectId>/workspaces/<workspaceId>/tasks/<taskId>`
  mají explicitní limit 4 KiB. Jde o bajty těla, ne počet znaků JSON.
- Limit se vynucuje při čtení streamu podle skutečných UTF-8 bajtů (ne až po
  `request.text()`); klientský `Content-Length` slouží jen k časnému odmítnutí.
  Překročení na cestě, která čte tělo, vrací `413 REQUEST_TOO_LARGE` bez
  vrácení vstupních dat. Workspace autorizuje vlastníka před čtením těla,
  takže neplatná capability zde vrací `404 OWNER_CAPABILITY_INVALID` i při
  nadlimitním těle; profile, watch a share naproti tomu mohou při syntakticky
  platné, ale neoprávněné capability vrátit 413 před databázovým ověřením.
  Tato politika se vztahuje jen na vyjmenované JSON request body; validace
  jednotlivých polí, uploady a limity odpovědí zůstávají samostatné.
- Čtení těla má celkový deadline 10 s od zahájení streamu; zaseknutý nebo
  pomalu dávkovaný stream vrací `408 REQUEST_TIMEOUT` bez vstupních dat a před
  jakoukoliv mutací DB. Pozdní čtení se zruší bez čekání na producenta.
  Deadline se záměrně nevztahuje na již zahájenou DB mutaci: timeout odpověď
  by jinak mohla skrýt úspěšně dokončený zápis. Slice #550 zavádí níže uvedený
  limit souběžnosti; runtime deadline a agregovaná měřitelnost zůstávají samostatnou prací.
- API Worker nyní přijme nejvýše 16 současně zpracovávaných běžných požadavků
  **v jednom izolátu**. Sedmnáctý a další dostanou `503` s JSON
  `{"error":"API_OVERLOADED"}`, `Retry-After: 1` (sekunda) a
  `Cache-Control: no-store`; tělo ani DB se u odmítnutého požadavku nezpracují. Slot se uvolní
  po dokončení odpovědi nebo chybě. `GET`/`HEAD /health` limit obcházejí.
  `GET`/`HEAD /ready` kontrolují D1 a mají oddělený limit 2 současných požadavků
  v jednom izolátu, takže je neblokuje zaplnění 16 běžných slotů. Třetí souběžný
  požadavek `/ready` dostane stejnou odpověď `503 API_OVERLOADED` s
  `Retry-After: 1` a `Cache-Control: no-store` bez přístupu k D1; slot se uvolní
  po úspěchu i chybě. Jiné metody `/health` a `/ready` podléhají běžnému limitu.
  Limity nejsou sdílené mezi izoláty ani instancemi, nejsou globálním rate limitem
  nebo ochranou proti distribuované zátěži a nestanovují deadline DB operace.
  Worker se pokusí zapsat nejvýše jedno vlastní varování `api_admission_overload`
  za minutu a izolát pro každou lane (`ordinary` nebo `ready`). Varování obsahuje
  číselné `occupancy`, `cap` a `rejectedSinceLast` (počet odmítnutí od posledního
  volání logovací funkce bez chyby, včetně aktuálního). Přijaté požadavky tuto událost
  nezapisují. Pouze vlastní payload této události neobsahuje URL, cestu, query,
  hlavičky, tokeny, tělo ani IP adresu; platformní Cloudflare invocation logy
  mohou obsahovat URL včetně query. Selhání logování nemění odpověď ani uvolnění
  slotů. Worker logy mohou být vzorkované nebo vypnuté. Tyto záznamy nejsou
  přesnými distribuovanými metrikami odmítnutí.
- Owner token projektu A nemůže spravovat projekt B.
- Chybné tělo watch/share se odmítá před přístupem k D1, bez zápisu;
  odpověď obsahuje jen stabilní chybový kód, nikoli jména polí ani hodnoty.
  Chybějící nebo neplatná owner capability zachovává externí odpověď
  `404 OWNER_CAPABILITY_INVALID` pro platný požadavek.
- Unknown/invalid share resolver neodhaluje existenci projektu.
- Share public projection neobsahuje applicant profile, owner principal, interní
  poznámky, dokumentové storage refs ani account/watch data.
