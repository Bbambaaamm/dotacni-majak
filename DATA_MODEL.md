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
- `applicant_profiles`
- `applicant_attribute_values`
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
