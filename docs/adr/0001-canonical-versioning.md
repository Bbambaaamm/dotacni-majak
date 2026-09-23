# ADR-0001: Canonical schema a immutable versioning

## Status
Accepted

## Decision
GrantCall je stabilní identita výzvy. GrantCallVersion je immutable snapshot jejích normalizovaných podmínek. DocumentVersion je rovněž immutable. Canonical schema má explicitní verzi.

## Consequences
- změny jsou auditovatelné,
- lze reprodukovat historické vyhodnocení,
- konektory nesmějí zapisovat přímo do canonical DB,
- změny schema vyžadují migration/compatibility review.
