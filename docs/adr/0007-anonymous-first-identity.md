# ADR-0007: Anonymní-first identita a účet až při synchronizaci / sdílení

## Status
Proposed (čeká na review).

## Context
Dotační maják musí umožnit první vyhledávání **bez registrace**. Uživatelé přicházejí hledat doporučení dotací, ne vytvářet účet. Účet (a případné spojení anonymních dat s identitou) je potřebný až při akcích, které vyžadují připomínky, sdílení, watch, nebo vlastnická práva nad projektem.

Zároveň nelze vycházet z předpokladu, že uživatel má social-login, e-mailovou adresu, ani jakýkoli externí identity provider k dispozici — první interakce musí fungovat pro kdokoliv, kdo našel webové rozhraní.

**Prior dura evidence** pro tento issue nebyla vytvořena; níže uvedené je ověřeno přímo na kódové základně aktuálního `main` (commit `5d9b7ed`).

## Decision

### 1. Anonymní capability jako základ identity
Projekt lze vytvořit bez registrace. Správu projektu chrání **jednorázově vydaný 256-bit owner capability token**:

- `POST /projects` vytvoří projekt s `owner_user_id = "anonymous:{projectId}"` a vrátí raw capability token jednou.
- Server ukládá do D1 **pouze domain-separated SHA-256 hash** tokenu (`project_owner_capabilities.token_hash`).
- Raw token se **nikdy neukládá ani neLoguje** na serveru — aby ztracení klíče neznamenalo reveální útok, ale zároveň umožňuje revokaci/rotaci na základě hashu.

Toto je **hotovo** a implementováno v:
- `packages/project-access` (Python doména): `ProjectOwnerCapabilityService` — `issue` / `verify` / `rotate` / `revoke`, audit události.
- `apps/api/src/projectAccess.ts` (API worker): stejný model přímo proti D1.

### 2. Read-only sdílení jako samostatná capability
Sdílený odkaz je **explicitní `PROJECT_READ_ONLY` capability** s vlastním tokenem, vlastním TTL (default 30 dní, max 365 dní) a revokací:

- `POST /projects/:id/shares` vytvoří read-only odkaz — vyžaduje Bearer owner capability, vytváří nový share token (hash ukládán, raw vrácen jednou).
- `GET /share/:token` resolver pozměňuje pouze **whitelisted projection**: `id, title, intent, currencyCode, estimatedTotalBudgetMinor, plannedStart, plannedEnd, updatedAt`.
- Resolver **nikdy nevrací** `owner_user_id`, `applicant_profile_id`, interní poznámky, document storage refs, watch ani account data. (Ověřeno v `apps/api/tests/index.test.ts`: mock ukazuje `owner_user_id: "must-never-leak"` a `applicant_profile_id: "must-never-leak"`, assertion kontroluje, že těla odpovědi tyto řetězce neobsahují.)
- Neznámý, zrušený i expirovaný odkaz se navenek nerozlišuje — vrací `404 SHARE_NOT_FOUND`.

Toto je **hotovo** a implementováno v:
- `packages/sharing` (Python doména): `ProjectSharingService` — `create` / `resolve` / `revoke`, audit události.
- `apps/api/src/share.ts` (resolver) + `apps/api/src/projectAccess.ts` (create/revoke).

### 3. Identita jako textový principal, nikoli pevný schéma
`owner_user_id` v databázi je **textový identifikátor**, nikoli cizí klíč k pevné tabulce uživatelů. Anonymní princip má tvar `anonymous:{projectId}`. To znamená:

- Existující anonymní projekty fungují i později bez změny schémata.
- Když se uživatelé budou přidělovat účty (account linking), `owner_user_id` se změní z `anonymous:{projectId}` na `user:{userId}` — **bez nutnosti měnit existující capability tokeny**, které jsou project-scoped, nikoli user-scoped.
- Account linking je tedy **migrace hodnoty v `owner_user_id`** a případné přiřazení existujících capability tokenů k nové identitě — nikoli předělání datového modelu.

### 4. Žádná hard dependency na specifický identity provider
Autentifikace je **abstrakcí**. Tento ADR neurčuje implementaci providera (email+heslo, social login, atd.). Capabilní model funguje bez něj — anonymní projekt a read-only sdílení jsou plně funkční bez jakékoli autentifikace. To splňuje požadavek "no social-login hard dependency".

### 5. Explicitní vlastnictví a least privilege
- Každý projekt má **právě jeden** `owner_user_id` — vlastnictví je jednoznačné.
- Watch / session / JavaScript storage **nemá vlastnická práva** — má pouze capability token pro daný projekt. To znamená, že stejný uživatel (stejný browser) může zpravovat více projektů, ale každý je chránen samostatným tokenem.
- Sdílení **neuděluje vlastnictví** ani měnící práva — jen `PROJECT_READ_ONLY`.
- Bez owner capability nelze měnit projekt, vytvářet sdílení, či měnit watch.

### 6. Revokace a rotace
- Owner capability lze **rotovat** (`POST /projects/:id/owner/rotate`) — nový token, starý přestane platit, generace se zvýší.
- Owner capability lze **revokovat** (`DELETE /projects/:id/owner/revoke`) — všechny operace nad projektem se zastaví.
- Read-only odkaz lze **revokovat** (`DELETE /projects/:id/shares/:shareId`) — idempotentní, non-disclosing (i neplatný požadavek vrátí 204).

## Account linking contract (návrh pro budoucí implementaci)
Následující body jsou **specifikací pro budoucí slice**, nikoli součástí implementovaného kódů v tomto PR. Jsou zahrnuty zde, aby bylo explicitní, jak bude anonymní data převzata účtem — tak, jak žádá scope tohoto issue ("účet až při synchronizaci/sdílení").

Když se uživatelé přidělují účty a account linking se provede:

1. `owner_user_id` anonymního projektu se změní z `anonymous:{projectId}` na `user:{userId}`.
2. Existující owner capability token zůstává **platný** (je project-scoped, nikoli user-scoped) — aby se nepřetržitost relace neporušila a uživatel neztratil správu projektu při přechodu na účet.
3. Sdílené odkazy zůstávají provázané s **projektem**, ne s uživatelem — jejich `owner_user_id` se aktualizuje na novou identitu vlastníka, ale token zůstává platný a revokovatelný.
4. Nové projekty se vytvoří s `owner_user_id = user:{userId}` a příslušným capability tokenem.
5. Sdílení je možné pouze pro projekty, které má caller ve vlastnictví (owner capability check proti `projects.owner_user_id`).
6. Zrušení / odpojení účtu by mělo způsobit, že projekt přechází zpět do stavu anonymního vlastníka (nebo do stavu bez vlastníka, dle rozhodnutí), ale **existující capability tokeny zůstávají funkční**, dokud nejsou revokovány — aby se neztrátily data.

Tento kontrakt zaručuje, že **anonymní data nejsou ztracena při přechodu na účet**, a že **účet nemůže znehodnotit existující anonymní capability** — oba požadavky scope.

## Privacy / retention dopad

- **Anonymní relace**: capability se ukládá v prohlížeči pouze do `sessionStorage` (ztrácí se po zavření relace). Nebylo provedeno ukládání do `localStorage` — uživatel je explicitně upozorněn, že ztracený anonymní správcovský klíč nelze bez budoucího account bindingu obnovit. (`ProjectsPage` / `projectSharing.ts`)
- **Server loguje audit události** (create / verify / rotate / revoke pro owner capability a create / resolve / revoke pro share), **nikoli raw tokeny**.
- **Read-only share odpovědi** mají `Cache-Control: private, no-store`, `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer` — jak na serveru, tak v HTML meta na sdílené stránce. (`apps/api/src/share.ts`, `SharedProjectPage`)
- **Retention policy** pro auth/security audit logy, anonymní session trackingu a anonymní telemetry **není ještě definitivně stanovená** — je součástí privacy architektury (issue #37, zatím close, ale retention bod je explicitně "před beta definovat"). Pro M12 je důležité, že anonymní relace **neukládají trvalá osobní data na serveru** — projekt je v DB, ale jeho vlastník je anonymní princip, ne osobní identifikátor.

## Consequences

- ✅ První search nevyžaduje registraci — hotovo (`/search`, `/grants/:id` jsou veřejné).
- ✅ Projekt lze založit anonymně — hotovo (`POST /projects` + owner capability).
- ✅ Read-only sdílení bez vlastnických prav — hotovo.
- ✅ Účet a account linking je navržen jako migrace `owner_user_id` — umožňuje postupný přechod bez přetržení existujících projektů a capability tokenů.
- ✅ Žádná hard dependency na specifický identity provider.
- ⚠️ Test coverage: ADR doporučuje, aby hlavní i chybový scénář pro `project-access` a `sharing` měl automatické testy — tyto testy jsou součástí tohoto PR (viz `tests/python/test_project_access.py`, `tests/python/test_sharing.py`).
- ⚠️ Accessibility review "accessible authentication" (ACCESSIBILITY.md) ještě nebyl proveden — protože autentifikační flow dosud nebyl implementován. Po implementaci account linking bude nutný. Viz sekce Accessibility níže.

## Accessibility a mobile — současný stav

**Hotovo (UI komponenty):**

- `ProjectsPage` — React komponenta s ARIA landmarks, `aria-labelledby`, `StatusBadge` komponentou pro stav (nepouze barva), explicitní formulářové label/placeholder, `role="status"` pro zprávy, `sessionStorage` pro aktivní projekt (bez `localStorage`).
- `SharedProjectPage` — `aria-busy`, `aria-label`, `<dl>`/`<dt>`/`<dd>` pro faktovou sadu, odkaz na hlavní stránku, noindex/nofollow/referrer-headers.
- `StatusBadge` — vizuální stav kombinuje ikonu + textový label (nepouze barva), což odpovídá požadavku ACCESSIBILITY.md "Status komponenty: používat text + ikonu + případně barvu".

**Pending (dosud neprovedeno, protože auth flow nebyl implementován):**

- ACCESSIBILITY.md uvádí povinný manuální review **"accessible authentication"** před betou — ten zatím nebyl proveden, protože autentifikační flow (login, registrace, account linking UI) dosud neexistuje.
- Jakmile bude implementován account linking, budou potřeba:
  - formuláře s jasnými label/instructions/error zprávami,
  - klávesovní navigace,
  - status zprávy o úspěchu/chybě jako `role="status"` / `aria-live`,
  - 200% zoom a reflow test.
- Tento ADR je zde proto, aby bylo explicitní, že **současný anonymní model je plně accessibility-tested u UI, které existuje**, a že pending review se týká pouze budoucího auth flow.

## Not covered by this ADR (intentionally)

- Implementace identity providera (email+heslo, social login) — je to budoucí slice.
- Retention čísel pro auth/security logy — je součástí privacy architektury (#37), explicitně "před beta definovat".
- Plnohodnotný account linking implementation — je to budoucí slice, návrh kontraktu je zde, implementace ne.
