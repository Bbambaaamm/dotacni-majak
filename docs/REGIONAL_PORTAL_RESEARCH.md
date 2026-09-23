# Remaining regional portal research

Issues: #63, #69, #71.

Verified on: **2026-09-23**

The Playwright probes observe only unauthenticated public traffic and log:
- public URL origin/path,
- method/resource type,
- query parameter names,
- JSON response **shape** (field names/types), not values.

They never log request/response bodies, cookies or authorization headers and do not bypass login, CAPTCHA or technical controls.

## Královéhradecký kraj — READY FOR CONNECTOR

Official public portal:

https://dotace.khk.cz/

The public homepage exposes a stable **Dotační oblasti** link:

https://dotace.khk.cz/grantProgram?year=2027&year=2026

This is sufficient as the initial HTML discovery route. Search-indexed official detail pages use the stable shape:

`https://dotace.khk.cz/grantProgram/{program-code}`

Examples observed from the official portal include programme codes such as:
- `25KPG30`
- `24POVU1`
- `25RRDU3`
- `25ZPD02`

Public browser traffic also exposes unauthenticated read-only dictionary endpoints on:

`https://dotisreactfunctions.azurewebsites.net`

including:
- GET `/api/Dictionary/GetProjectCollection`
- GET `/api/Dictionary/GetMinMaxProjectYear`
- GET `/api/Dictionary/GetDistrictCollection`
- GET `/api/Dictionary/GetLegalTitlesCollection`

However, these endpoints are **not** treated as the grant catalogue until their semantics are independently proven. In particular, `GetProjectCollection` must not be guessed to mean grant programmes merely because its name contains “Project”.

Connector v0.1 should therefore use:
1. official server/public HTML discovery at `/grantProgram?year=...`,
2. official `/grantProgram/{code}` detail pages,
3. document links from those detail pages,
4. RAW snapshots for both listing and detail.

No login/request endpoints are needed.

## Středočeský kraj — RESEARCH REQUIRED

Target:

https://dotace.stredoceskykraj.cz/

The public portal was not reliably retrievable from the GitHub-hosted browser probe during this research pass (navigation timeout / no stable public XHR contract captured).

Search engines expose public pages such as grant-calculator routes, but that is not enough evidence for a stable catalogue contract.

Do not implement a guessed connector. Next research should prefer:
- official export/open-data route if one exists,
- simple public HTML/HTTP retrieval diagnostics,
- a documented public catalogue URL.

## Kraj Vysočina — LIMITED / ALTERNATIVE SOURCE REQUIRED

Target:

https://www.fondvysociny.cz/

The public GitHub-hosted probe received an explicit **“Požadavek odmítnut”** response and no usable public XHR contract.

This technical control must not be bypassed.

Next research should look for an alternative official source such as:
- krajský open-data/export feed,
- official programme documents/index outside the protected portal,
- another documented public endpoint.

Until then Source Coverage must report the source as limited rather than pretending complete monitoring.

## Decision

A connector is implemented only after a public stable retrieval route or a server-rendered official listing is verified.

Current result:
- KHK: **implement now**
- Středočeský: **continue research**
- Vysočina: **find alternate official source; do not bypass portal protection**
