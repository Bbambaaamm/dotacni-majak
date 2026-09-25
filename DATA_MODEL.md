# Canonical Data Model v1

## Stabilní identity
- `providers`
- `programmes`
- `grant_calls` — stabilní identita výzvy
- `grant_call_versions` — immutable podmínky v čase

## Sources / ingestion
- `source_registry`
- `source_runs`
- `source_records`
- `source_checkpoints`
- `ingestion_runs`
- `ingestion_items`
- `data_quality_issues`
- `quarantine_items`
- `outbox_events`

## Documents / provenance
- `source_documents`
- `document_versions`
- `document_sections`
- `field_evidence`

## Geography
- `geographies` — hierarchie COUNTRY/NUTS/REGION/DISTRICT/ORP/MUNICIPALITY/MAS s validitou a kódy NUTS/LAU/ORP/MAS
- `grant_geographies` — INCLUDE/EXCLUDE pravidlo nad konkrétní GrantCallVersion; zvlášť pro PROJECT_LOCATION / APPLICANT_SEAT / BOTH

## Funding
- `grant_deadlines`
- `grant_geographies`
- `funding_scenarios`
- `cost_categories`
- `grant_cost_rules`
- `grant_requirements`

## Ontology/search
- `ontology_terms`
- `ontology_edges`
- `ontology_synonyms`
- `grant_ontology_terms`
- `grant_search_fts`
- `search_profiles`
- `grant_matches`

## Eligibility
- `attribute_definitions`
- `applicant_types`
- `eligibility_rule_sets`
- `rule_groups`
- `rule_conditions`
- `eligibility_evaluations`
- `condition_results`

Interní condition result: PASS / FAIL / UNKNOWN / ERROR / NOT_APPLICABLE.

Veřejný result: ELIGIBLE / LIKELY_ELIGIBLE / NEEDS_INFORMATION / INELIGIBLE / NEEDS_REVIEW.

## Users/projects
- `applicant_types` — verzovatelná hierarchie typů žadatelů; v canonical v1 koexistuje s legacy `ApplicantProfile.applicantType` enumem kvůli kompatibilitě
- `applicant_profiles` — často filtrované profilové údaje; `fieldSources` drží provenance/verification metadata po poli
- `applicant_attribute_values` — řídké dynamické atributy navázané na AttributeDefinition, včetně valueType/sourceKind/verificationStatus
- `projects`
- `project_attribute_values`

## Workspace/monitoring
- `application_workspaces`
- `workspace_tasks`
- `change_events`
- `watches`
- `watch_matches`
- `notifications`

## History
- `historical_awards`
- `historical_award_ontology_terms`

## Pravidla modelu
- Často filtrované hodnoty = normální SQL sloupce.
- JSON = snapshoty a řídké/dynamické hodnoty.
- Každá kritická podmínka/finance/deadline musí být dohledatelná přes `field_evidence`.
- Historická podpora nikdy není aktivní výzva.


## Eligibility DSL invariants

Attribute Registry používá stabilní klíče `applicant.*` / `project.*`.
Rules jsou strom `RuleSet → RuleGroup → RuleCondition`.

- Group: AND / OR / NOT
- Žádný arbitrary eval/script.
- UNKNOWN policy: PROPAGATE / NOT_APPLICABLE; nikdy FAIL.
- Jeden RuleSet může mít nejvýše jeden root group na DB úrovni; evaluator vyžaduje právě jeden.
- RuleCondition může mít provenance přes `field_evidence`.


## Runtime persistence ingestionu

Runtime tabulky:
- `source_checkpoints` — poslední bezpečně commitnutý discovery checkpoint,
- `ingestion_runs` — stav, metriky a checkpoint before/after každého běhu,
- `ingestion_items` — per-run retry/idempotence state source identity,
- `ingestion_locks` — source-level lease s expirací.

Tyto tabulky neobsahují canonical fakta o dotaci. Řídí pouze spolehlivost
zpracování; canonical data zůstávají v GrantCall/GrantCallVersion/document/
evidence doméně.
