# ADR-0002: RAW-first ingestion

## Status
Accepted

## Decision
Každý externí záznam nebo dokument se nejdřív uloží jako RAW snapshot s URL, časem, MIME a SHA-256. Až následně se parsuje a normalizuje.

## Consequences
- parser lze znovu spustit bez nového downloadu,
- máme audit trail,
- nevalidní nová verze může skončit v quarantine bez poškození poslední publikované verze.
