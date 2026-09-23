# ADR-0003: Source Adapter Contract v1

## Status
Accepted

## Decision
Konektory implementují healthcheck/discover/fetch_record/fetch_artifact a veškerou síťovou komunikaci vedou přes GuardedHttpClient.

## Consequences
- jednotné contract tests,
- centralizovaný rate limit a SSRF ochrana,
- adapter nemůže rozhodovat eligibility ani publikovat do canonical DB.
