# Středočeský kraj — lightweight public HTTP research

Issue: #63

The headless-browser probes against the county site timed out even though public
pages are indexed and accessible externally. This probe deliberately removes the
browser layer and uses only a normal HTTPS GET against the county's public search:

`https://idzsck.stredoceskykraj.cz/web/urad/vyhledavani?q=Program%202026`

The public search route and `q` parameter are visible on the official county
website. The probe retains only same-domain public programme/document links.

## Safety
- HTTPS verification remains enabled
- no login
- no cookies/session
- no authorization headers
- no request body
- no CAPTCHA bypass
- no protected electronic application portal

If even this simple route is unavailable from the ingestion environment, the
correct product behavior is an explicit Source Coverage limitation, not a bypass.
