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


## Public index contract

Discovery starts at:

`https://www.kr-vysocina.cz/vismo/rejstrik.asp?id_org=450008&p1=122604&p3=.&rh=397`

The official index publicly exposes pagination with `pocet=24&stranka=N`. The adapter discovers those same-origin page links rather than assuming a fixed number of pages.

A public article is only a grant candidate when its text clearly signals programme announcement/application intake for the current year. Historical awards/results remain news context and are excluded from active-call discovery.
