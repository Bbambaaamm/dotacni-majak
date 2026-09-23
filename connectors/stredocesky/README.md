# Středočeský kraj connector

Issue: #63

Coverage is intentionally **LIMITED**.

The connector starts from the official public county page:

`https://stredoceskykraj.cz/web/urad/dotace`

It follows the public link labelled as the current **Příručka středočeských fondů** and parses the public PDF as the authoritative discovery source for programmes listed in that guide.

## What is covered

- programmes/rules listed in the current official Středočeské fondy guide,
- application windows where they can be proven from the guide,
- allocation text,
- applicant text,
- grant amount text,
- co-financing text,
- page-level source provenance,
- RAW snapshots of the landing page and guide PDF.

## What is NOT claimed

- complete coverage of every Středočeský funding instrument,
- protected Electronic Grant Portal (EDP) catalogue,
- programmes absent from the current guide.

The protected application portal is not bypassed. Source Coverage must display this connector as LIMITED.

## Runtime reachability

GitHub-hosted live smoke currently observes a transport timeout to the official
county site. This is represented as a Source Health limitation, not hidden or
worked around. If the source becomes reachable, the same smoke validates
discovery and parsing. Until then public coverage must remain DEGRADED/LIMITED.
