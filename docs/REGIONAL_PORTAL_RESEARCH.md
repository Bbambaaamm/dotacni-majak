# Remaining regional portal research

Issues: #63, #69, #71.

The Playwright probe observes only unauthenticated public traffic and logs:
- public URL origin/path,
- method/resource type,
- query parameter names,
- JSON response **shape** (field names/types), not values.

It never logs request/response bodies, cookies or authorization headers and does not bypass login, CAPTCHA or technical controls.

Targets:
- Středočeský kraj: https://dotace.stredoceskykraj.cz/
- Královéhradecký kraj: https://dotace.khk.cz/
- Kraj Vysočina: https://www.fondvysociny.cz/

A connector is implemented only after a public stable retrieval route or a server-rendered official listing is verified.
