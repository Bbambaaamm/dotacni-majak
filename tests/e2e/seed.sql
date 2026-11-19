PRAGMA foreign_keys = ON;

INSERT INTO providers(id,name,provider_type,official_url)
VALUES
  ('e2e-provider-open','E2E test provider A','NATIONAL','https://example.invalid/provider-a'),
  ('e2e-provider-planned','E2E test provider B','NATIONAL','https://example.invalid/provider-b'),
  ('e2e-provider-nsa','Národní sportovní agentura','NATIONAL','https://nsa.gov.cz/');

INSERT INTO programmes(id,provider_id,name,funding_origin,official_url)
VALUES
  ('e2e-programme-open','e2e-provider-open','E2E Digitalizace A','CZ_NATIONAL','https://example.invalid/programme-a'),
  ('e2e-programme-planned','e2e-provider-planned','E2E Digitalizace B','CZ_NATIONAL','https://example.invalid/programme-b'),
  ('e2e-programme-nsa','e2e-provider-nsa','NSA — Investiční výzvy','CZ_NATIONAL','https://nsa.gov.cz/');

INSERT INTO source_registry(
  id,code,name,base_url,adapter_key,authority,retrieval_mode,
  refresh_minutes,enabled,priority
) VALUES
  ('e2e-source-open','E2E_A','E2E oficiální zdroj A','https://example.invalid/','e2e-a','OFFICIAL','JSON',60,1,10),
  ('e2e-source-planned','E2E_B','E2E oficiální zdroj B','https://example.invalid/','e2e-b','OFFICIAL','JSON',60,1,10),
  ('e2e-source-nsa','NSA_E2E','Národní sportovní agentura','https://nsa.gov.cz/','nsa-e2e','OFFICIAL','HTML',60,1,10);

INSERT INTO grant_calls(
  id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,
  created_at,updated_at
) VALUES
  ('grant:e2e:open','e2e-programme-open','E2E-OPEN','e2e-open-digitalizace',NULL,'OPEN',
   'E2E otevřená výzva — digitalizace obce','2026-09-20T08:00:00Z','2026-09-20T08:00:00Z',
   '2026-09-20T08:00:00Z','2026-09-26T20:00:00Z'),
  ('grant:e2e:planned','e2e-programme-planned','E2E-PLANNED','e2e-planned-digitalizace',NULL,'PLANNED',
   'E2E plánovaná výzva — digitalizace obce','2026-09-20T08:00:00Z','2026-09-20T08:00:00Z',
   '2026-09-20T08:00:00Z','2026-09-26T20:00:00Z'),
  ('grant:e2e:nsa-closed','e2e-programme-nsa','16/2026','e2e-nsa-regiony-2026',NULL,'CLOSED',
   'Regiony 2026 — investice pod 10 mil. Kč (historický E2E fixture)',
   '2026-01-01T08:00:00Z','2026-01-01T08:00:00Z',
   '2026-01-01T08:00:00Z','2026-09-26T20:00:00Z');

INSERT INTO grant_call_versions(
  id,grant_call_id,version_number,captured_at,title,summary,status,
  published_at,submission_open_at,submission_close_at,official_detail_url,
  currency_code,normalization_version,content_hash,verification_status,created_at
) VALUES
  ('gcv-e2e-open','grant:e2e:open',1,'2026-09-26T20:00:00Z',
   'E2E otevřená výzva — digitalizace obce',
   'Deterministický nesportovní E2E záznam pro ověření celé UI/API cesty.',
   'OPEN','2026-09-20T08:00:00Z','2026-09-20T08:00:00Z','2027-12-31T23:59:59Z',
   'https://example.invalid/e2e/open','CZK','e2e-v1',
   'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','VERIFIED',
   '2026-09-26T20:00:00Z'),
  ('gcv-e2e-planned','grant:e2e:planned',1,'2026-09-26T20:00:00Z',
   'E2E plánovaná výzva — digitalizace obce',
   'Druhý deterministický výsledek pro browser filter coverage.',
   'PLANNED','2026-09-20T08:00:00Z',NULL,'2027-10-31T23:59:59Z',
   'https://example.invalid/e2e/planned','CZK','e2e-v1',
   'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','VERIFIED',
   '2026-09-26T20:00:00Z'),
  ('gcv-e2e-nsa-closed','grant:e2e:nsa-closed',1,'2026-09-23T08:00:00Z',
   'Regiony 2026 — investice pod 10 mil. Kč (historický E2E fixture)',
   'Výstavba a technické zhodnocení sportovních zařízení místního významu.',
   'CLOSED','2026-01-01T08:00:00Z','2025-12-01T00:00:00Z','2026-01-19T23:59:59Z',
   'https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/',
   'CZK','e2e-v1',
   'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','PARTIALLY_VERIFIED',
   '2026-09-23T08:00:00Z');

UPDATE grant_calls SET current_version_id='gcv-e2e-open'
WHERE id='grant:e2e:open';
UPDATE grant_calls SET current_version_id='gcv-e2e-planned'
WHERE id='grant:e2e:planned';
UPDATE grant_calls SET current_version_id='gcv-e2e-nsa-closed'
WHERE id='grant:e2e:nsa-closed';

INSERT INTO source_records(
  id,source_id,external_id,canonical_url,record_type,grant_call_id,
  first_seen_at,last_seen_at,presence_state,missing_run_count,content_hash
) VALUES
  ('e2e-sr-open','e2e-source-open','E2E-OPEN','https://example.invalid/e2e/open',
   'GRANT_CALL','grant:e2e:open','2026-09-20T08:00:00Z','2026-10-01T09:00:00Z','SEEN',0,
   'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
  ('e2e-sr-planned','e2e-source-planned','E2E-PLANNED','https://example.invalid/e2e/planned',
   'GRANT_CALL','grant:e2e:planned','2026-09-20T08:00:00Z','2026-09-26T20:00:00Z','SEEN',0,
   'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'),
  ('e2e-sr-nsa','e2e-source-nsa','16/2026',
   'https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/',
   'GRANT_CALL','grant:e2e:nsa-closed','2026-01-01T08:00:00Z','2026-09-23T08:00:00Z','SEEN',0,
   'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc');

INSERT INTO source_documents(
  id,grant_call_id,source_id,document_type,title,source_url,first_seen_at,last_seen_at
) VALUES
  ('e2e-doc-open','grant:e2e:open','e2e-source-open','CALL_DOCUMENT',
   'E2E oficiální podmínky','https://example.invalid/e2e/open-source',
   '2026-09-20T08:00:00Z','2026-09-26T20:00:00Z');

INSERT INTO document_versions(
  id,source_document_id,sha256,retrieved_at,mime_type,file_size,object_key,
  parser_version,extraction_status,page_count,language_code
) VALUES
  ('e2e-dv-open','e2e-doc-open',
   'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
   '2026-09-26T20:00:00Z','application/pdf',128,'raw/E2E/e2e-open.pdf',
   'e2e-v1','EXTRACTED',2,'cs');

INSERT INTO field_evidence(
  id,entity_type,entity_id,field_path,document_version_id,
  page_from,page_to,evidence_text,extraction_method,extractor_version,
  confidence_ppm,verification_status,created_at
) VALUES
  ('e2e-fe-title','GRANT_CALL_VERSION','gcv-e2e-open','/title','e2e-dv-open',
   1,1,'E2E otevřená výzva — digitalizace obce','E2E_SEED','e2e-v1',
   1000000,'VERIFIED','2026-09-26T20:00:00Z'),
  ('e2e-fe-summary','GRANT_CALL_VERSION','gcv-e2e-open','/summary','e2e-dv-open',
   1,1,'Deterministický nesportovní E2E záznam pro ověření celé UI/API cesty.',
   'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z'),
  ('e2e-fe-deadline','GRANT_CALL_VERSION','gcv-e2e-open','/submission_close_at','e2e-dv-open',
   2,2,'Příjem žádostí do 31. prosince 2027, 23:59:59 UTC',
   'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z'),
  ('e2e-fe-applicant-type','GRANT_CALL_VERSION','gcv-e2e-open','/eligibility/applicant.type','e2e-dv-open',
   1,1,'Pouze syntetický E2E test: žadatel je obec.',
   'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z'),
  ('e2e-fe-funding','GRANT_CALL_VERSION','gcv-e2e-open','/funding_scenarios/e2e-funding-open','e2e-dv-open',
   3,3,'Pouze syntetický E2E test: max. dotace 100 000 Kč.',
   'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z');

INSERT INTO funding_scenarios(id,grant_call_version_id,name,currency_code,support_rate_max_bps,grant_amount_max_minor,evidence_id)
VALUES ('e2e-funding-open','gcv-e2e-open','E2E syntetický scénář','CZK',6000,10000000,'e2e-fe-funding'),
       ('e2e-funding-undocumented','gcv-e2e-open','E2E scénář bez samostatného dokladu','CZK',NULL,NULL,NULL);

-- Non-grant sentinel: grant-shaped legacy fields must not become a claimed loan amount or grant.
UPDATE grant_call_versions SET funding_instrument_type='LOAN' WHERE id='gcv-e2e-planned';
INSERT INTO funding_scenarios(id,grant_call_version_id,name,instrument_type,currency_code,support_rate_max_bps,grant_amount_max_minor)
VALUES ('e2e-funding-loan','gcv-e2e-planned','E2E syntetický úvěr','LOAN','CZK',7000,1234500),
       ('e2e-funding-mismatch','gcv-e2e-planned','E2E rozpor typu výzvy a scénáře','GRANT','CZK',8000,9876500);

-- Synthetic rule for the browser UNKNOWN -> declared answer -> fresh evaluation proof.
-- It is test data only; it must never imply actual conditions of an official call.
INSERT INTO eligibility_rule_sets(id,grant_call_version_id,name,completeness_status,verification_status)
VALUES ('e2e-rule-set-open','gcv-e2e-open','E2E syntetický typ žadatele','COMPLETE','VERIFIED');
INSERT INTO rule_groups(id,rule_set_id,group_operator)
VALUES ('e2e-rule-root-open','e2e-rule-set-open','AND');
INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,
  expected_value_json,verification_status,evidence_id)
VALUES ('e2e-applicant-type','e2e-rule-root-open','attr-applicant-type','EQ',
  '"MUNICIPALITY"','VERIFIED','e2e-fe-applicant-type');

INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,ends_at,timezone,description,evidence_id)
VALUES ('e2e-deadline-open','gcv-e2e-open','APPLICATION_CLOSE',
        '2027-12-31T23:59:59Z','UTC','Přesný konec příjmu žádostí','e2e-fe-deadline');

INSERT INTO grant_requirements(id,grant_call_version_id,requirement_type,title,necessity,evidence_id)
VALUES
  ('e2e-req-budget','gcv-e2e-open','DOCUMENT','Připravit rozpočet projektu','REQUIRED','e2e-fe-summary'),
  ('e2e-req-permit','gcv-e2e-open','PERMIT','Ověřit potřebu stavebního povolení','CONDITIONAL',NULL),
  ('e2e-req-consult','gcv-e2e-open','ACTION','Konzultovat žádost s poskytovatelem','RECOMMENDED',NULL);

INSERT INTO grant_search_documents(
  grant_call_version_id,title,summary,supported_activities,eligible_costs,
  keywords,status,submission_close_at,updated_at
) VALUES
  ('gcv-e2e-open','E2E otevřená výzva — digitalizace obce',
   'Deterministický nesportovní E2E záznam pro ověření celé UI/API cesty.',
   'digitalizace obce veřejná správa','','digitalizace obce e2e','OPEN',
   '2027-12-31T23:59:59Z','2026-09-26T20:00:00Z'),
  ('gcv-e2e-planned','E2E plánovaná výzva — digitalizace obce',
   'Druhý deterministický výsledek pro browser filter coverage.',
   'digitalizace obce plánovaná podpora','','digitalizace obce e2e','PLANNED',
   '2027-10-31T23:59:59Z','2026-09-26T20:00:00Z'),
  ('gcv-e2e-nsa-closed','Regiony 2026 — investice pod 10 mil. Kč (historický E2E fixture)',
   'Výstavba a technické zhodnocení sportovních zařízení místního významu.',
   'rekonstrukce tenisových kurtů sportovní zařízení sportovní infrastruktura',
   '','tenis kurt rekonstrukce sport','CLOSED','2026-01-19T23:59:59Z',
   '2026-09-26T20:00:00Z');

-- Dedicated pagination dataset; it does not match the existing journey intents.
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 25)
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
SELECT 'grant:e2e:page:' || i,CASE WHEN i = 25 THEN 'e2e-programme-planned' ELSE 'e2e-programme-open' END,'E2E-PAGE-' || i,
  'e2e-page-' || i,NULL,CASE WHEN i = 25 THEN 'PLANNED' ELSE 'OPEN' END,
  CASE WHEN i = 25 THEN 'E2E pozdější plánovaná výzva' ELSE 'E2E stránkování ' || i END,
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z' FROM n;

WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 25)
INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  submission_close_at,official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-page-' || i,'grant:e2e:page:' || i,1,'2026-09-26T20:00:00Z',
  CASE WHEN i = 25 THEN 'E2E pozdější plánovaná výzva' ELSE 'E2E stránkování ' || i END,
  'Testovací záznam stránkování.',CASE WHEN i = 25 THEN 'PLANNED' ELSE 'OPEN' END,
  CASE WHEN i = 25 THEN '2027-05-01T00:00:00Z' ELSE NULL END,
  'https://example.invalid/e2e/page/' || i,'CZK','e2e-v1',
  printf('%064d',i),'VERIFIED','2026-09-26T20:00:00Z' FROM n;

UPDATE grant_calls SET current_version_id = 'gcv-e2e-page-' || substr(id, length('grant:e2e:page:') + 1)
WHERE id LIKE 'grant:e2e:page:%';

WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 25)
INSERT INTO source_records(id,source_id,external_id,canonical_url,record_type,grant_call_id,
  first_seen_at,last_seen_at,presence_state,missing_run_count,content_hash)
SELECT 'e2e-sr-page-' || i,'e2e-source-open','E2E-PAGE-' || i,
  'https://example.invalid/e2e/page/' || i,'GRANT_CALL','grant:e2e:page:' || i,
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z','SEEN',0,printf('%064d',i) FROM n;

WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 25)
INSERT INTO grant_search_documents(grant_call_version_id,title,summary,supported_activities,
  eligible_costs,keywords,status,submission_close_at,updated_at)
SELECT 'gcv-e2e-page-' || i,
  CASE WHEN i = 25 THEN 'E2E pozdější plánovaná výzva' ELSE 'E2E stránkování ' || i END,
  'Testovací záznam stránkování.',CASE WHEN i = 25 THEN '' ELSE 'strankovani' END,'',
  CASE i WHEN 1 THEN 'koupaliště' WHEN 2 THEN 'plavecké zařízení'
    WHEN 3 THEN 'plavecké zařízení' WHEN 25 THEN 'strankovani' ELSE '' END,
  CASE WHEN i = 25 THEN 'PLANNED' ELSE 'OPEN' END,
  CASE WHEN i = 25 THEN '2027-05-01T00:00:00Z' ELSE NULL END,
  '2026-09-26T20:00:00Z' FROM n;

-- Isolated source-date cases for bounded search; they do not match journey intents.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
SELECT 'grant:e2e:date:' || kind,'e2e-programme-open','E2E-DATE-' || kind,
  'e2e-date-' || kind,NULL,'OPEN','E2E date ' || kind,
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z'
FROM (SELECT 'only' AS kind UNION ALL SELECT 'invalid' UNION ALL SELECT 'malformed' UNION ALL SELECT 'null');

INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  submission_close_at,official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-date-' || kind,'grant:e2e:date:' || kind,1,'2026-09-26T20:00:00Z',
  'E2E date ' || kind,'date-boundary fixture','OPEN',close_at,
  'https://example.invalid/e2e/date/' || kind,'CZK','e2e-v1',printf('%064d',100 + ordinal),
  'VERIFIED','2026-09-26T20:00:00Z'
FROM (SELECT 'only' AS kind,'2027-05-01' AS close_at,1 AS ordinal
  UNION ALL SELECT 'invalid','2027-02-30',2
  UNION ALL SELECT 'malformed','not-a-date',3
  UNION ALL SELECT 'null',NULL,4);

UPDATE grant_calls SET current_version_id = 'gcv-e2e-date-' || substr(id, length('grant:e2e:date:') + 1)
WHERE id LIKE 'grant:e2e:date:%';

INSERT INTO grant_search_documents(grant_call_version_id,title,summary,supported_activities,
  eligible_costs,keywords,status,submission_close_at,updated_at)
SELECT id,title,summary,'date-boundary','','date-boundary',status,submission_close_at,
  '2026-09-26T20:00:00Z' FROM grant_call_versions WHERE id LIKE 'gcv-e2e-date-%';

-- Preserve the true UTC day at a sub-millisecond midnight boundary.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
SELECT 'grant:e2e:precision:' || kind,'e2e-programme-open','E2E-PRECISION-' || kind,
  'e2e-precision-' || kind,NULL,'OPEN','E2E precision ' || kind,
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z'
FROM (SELECT 'before' AS kind UNION ALL SELECT 'after');

INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  submission_close_at,official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-precision-' || kind,'grant:e2e:precision:' || kind,1,'2026-09-26T20:00:00Z',
  'E2E precision ' || kind,'precision-boundary fixture','OPEN',close_at,
  'https://example.invalid/e2e/precision/' || kind,'CZK','e2e-v1',printf('%064d',200 + ordinal),
  'VERIFIED','2026-09-26T20:00:00Z'
FROM (SELECT 'before' AS kind,'2027-05-01T23:59:59.9995Z' AS close_at,1 AS ordinal
  UNION ALL SELECT 'after','2027-05-02T00:00:00.0001Z',2);

UPDATE grant_calls SET current_version_id = 'gcv-e2e-precision-' || substr(id, length('grant:e2e:precision:') + 1)
WHERE id LIKE 'grant:e2e:precision:%';

INSERT INTO grant_search_documents(grant_call_version_id,title,summary,supported_activities,
  eligible_costs,keywords,status,submission_close_at,updated_at)
SELECT id,title,summary,'precision-boundary','','precision-boundary',status,submission_close_at,
  '2026-09-26T20:00:00Z' FROM grant_call_versions WHERE id LIKE 'gcv-e2e-precision-%';
