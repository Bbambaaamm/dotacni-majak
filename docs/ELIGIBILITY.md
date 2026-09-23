# Eligibility Engine

## Separation
Search odpovídá: „Je výzva tematicky relevantní?“
Eligibility odpovídá: „Splňuje tento konkrétní žadatel známé podmínky?“

Tyto výsledky se nesmí sloučit do jednoho skóre.

## Condition state
- PASS
- FAIL
- UNKNOWN
- ERROR
- NOT_APPLICABLE

## Public state
- ELIGIBLE
- LIKELY_ELIGIBLE
- NEEDS_INFORMATION
- INELIGIBLE
- NEEDS_REVIEW

## Safety rules

### UNKNOWN != FAIL
Chybějící údaj (např. vlastnictví sportoviště) znamená NEEDS_INFORMATION, ne INELIGIBLE.

### Definitivní INELIGIBLE
Vzniká pouze z blocking FAIL podmínek, které jsou VERIFIED.

Neověřený/extrahovaný FAIL → NEEDS_REVIEW.

### ELIGIBLE
Definitivní ELIGIBLE vyžaduje:
- root PASS,
- COMPLETE rule set,
- VERIFIED rule set,
- relevantní blocking conditions VERIFIED.

Jinak PASS → LIKELY_ELIGIBLE.

### Non-blocking conditions
Vyhodnotí se a zobrazí, ale jejich FAIL neblokuje eligibility.

### Geography
GEO_WITHIN/GEO_NOT_WITHIN vyžaduje explicitní GeographyResolver.
Bez resolveru → UNKNOWN.

## Reproducibility
Každé vyhodnocení má:
- engine_version
- evaluated_at
- stable SHA-256 input_snapshot_hash
- condition-level results/reason codes

Persistentní vrstva může ukládat i canonical input snapshot JSON, aby šlo historické rozhodnutí reprodukovat.
