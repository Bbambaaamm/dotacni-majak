# JDP / RISPF public retrieval research

Issue: #15

## Safety boundary

Research targets only the public, unauthenticated entry page:

- https://jdp2.mf.gov.cz/

The probe:
- uses a normal headless browser,
- does **not** log cookies, authorization headers, request bodies or response bodies,
- records only public request method, resource type, origin, path and query-parameter names,
- does not log in,
- does not bypass CAPTCHA or anti-bot controls,
- does not call guessed endpoints.

## Goal

Identify whether the public application itself exposes a stable read-only catalog/API that can be documented and then implemented through GuardedHttpClient.

If no such public retrieval route is observed, #15 remains research-blocked and JDP coverage continues through provider-specific official sources rather than an invented API.
