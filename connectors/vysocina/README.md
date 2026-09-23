# Kraj Vysočina connector

Issue: #71

Coverage is intentionally **LIMITED**.

The connector monitors the official public `kr-vysocina.cz` index tagged
`Fond Vysočiny`, follows only same-origin public articles that clearly announce
a programme/application window, and ignores result/award news.

The protected `fondvysociny.cz` catalogue is not bypassed.

## Discovery
Public index:
`/vismo/rejstrik.asp?id_org=450008&p1=122604&p3=.&rh=397`

Pagination is public and stable via `pocet=24&stranka=N`.

## Safety
- RAW-first
- same-origin only
- no login/CAPTCHA bypass
- aggregate roundup articles are excluded rather than incorrectly converted
  into one grant call
- if exact application dates cannot be proven, status remains ANNOUNCED
