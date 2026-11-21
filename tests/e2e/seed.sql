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
  ('grant:e2e:unsafe-url','e2e-programme-open','E2E-UNSAFE-URL','e2e-unsafe-url',NULL,'PLANNED',
   'E2E výzva — bezpečnost odkazu','2026-09-20T08:00:00Z','2026-09-20T08:00:00Z',
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
  ('gcv-e2e-unsafe-url','grant:e2e:unsafe-url',1,'2026-09-26T20:00:00Z',
   'E2E výzva — bezpečnost odkazu','Syntetický poškozený odkaz pouze pro E2E test.',
   'PLANNED','2026-09-20T08:00:00Z',NULL,NULL,
   'javascript:alert(1)','CZK','e2e-v1',
   'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee','NEEDS_REVIEW',
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
UPDATE grant_calls SET current_version_id='gcv-e2e-unsafe-url'
WHERE id='grant:e2e:unsafe-url';
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
  ('e2e-sr-unsafe-url','e2e-source-open','E2E-UNSAFE-URL','javascript:alert(2)',
   'GRANT_CALL','grant:e2e:unsafe-url','2026-09-20T08:00:00Z','2026-09-26T20:00:00Z','SEEN',0,
   'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'),
  ('e2e-sr-nsa','e2e-source-nsa','16/2026',
   'https://nsa.gov.cz/dotace/vyzva-16-2026-regiony-26-investice-pod-10-mil-kc/',
   'GRANT_CALL','grant:e2e:nsa-closed','2026-01-01T08:00:00Z','2026-09-23T08:00:00Z','SEEN',0,
   'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc');

INSERT INTO source_documents(
  id,grant_call_id,source_id,document_type,title,source_url,first_seen_at,last_seen_at
) VALUES
  ('e2e-doc-open','grant:e2e:open','e2e-source-open','CALL_DOCUMENT',
   'E2E oficiální podmínky','https://example.invalid/e2e/open-source',
   '2026-09-20T08:00:00Z','2026-09-26T20:00:00Z'),
  ('e2e-doc-uncertain','grant:e2e:unsafe-url','e2e-source-open','CALL_DOCUMENT',
   'E2E doklad s neověřitelným datem stažení','https://example.invalid/e2e/uncertain-source',
   '2026-09-20T08:00:00Z','2026-09-26T20:00:00Z');

INSERT INTO document_versions(
  id,source_document_id,sha256,retrieved_at,mime_type,file_size,object_key,
  parser_version,extraction_status,page_count,language_code
) VALUES
  ('e2e-dv-open','e2e-doc-open',
   'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
   '2026-09-26T20:00:00Z','application/pdf',128,'raw/E2E/e2e-open.pdf',
   'e2e-v1','EXTRACTED',2,'cs'),
  ('e2e-dv-uncertain','e2e-doc-uncertain',
   'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
   '2026-02-30T12:00:00Z','application/pdf',128,'raw/E2E/e2e-uncertain.pdf',
   'e2e-v1','EXTRACTED',1,'cs');

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
   3,3,'Pouze syntetický E2E test: spodní mez dotace 50 000 Kč a strop 100 000 Kč podle scénáře, náklady projektu 200 000–400 000 Kč, platba po úhradě, bez zálohy.',
   'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z'),
  ('e2e-fe-uncertain','GRANT_CALL_VERSION','gcv-e2e-unsafe-url','/summary','e2e-dv-uncertain',
   1,1,'Syntetický doklad s chybným datem stažení.',
   'E2E_SEED','e2e-v1',1000000,'NEEDS_REVIEW','2026-09-26T20:00:00Z');

INSERT INTO funding_scenarios(id,grant_call_version_id,name,currency_code,support_rate_max_bps,grant_amount_min_minor,grant_amount_max_minor,project_cost_min_minor,project_cost_max_minor,payment_mode,advance_payment_allowed,evidence_id)
VALUES ('e2e-funding-open','gcv-e2e-open','E2E syntetický scénář','CZK',6000,5000000,10000000,20000000,40000000,'REIMBURSEMENT',0,'e2e-fe-funding'),
       ('e2e-funding-undocumented','gcv-e2e-open','E2E scénář bez samostatného dokladu','CZK',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
-- Only lower bounds are known; no upper rate, upper grant amount or personal award can be inferred.
INSERT INTO funding_scenarios(id,grant_call_version_id,name,currency_code,support_rate_min_bps,grant_amount_min_minor)
VALUES ('e2e-funding-min-only','gcv-e2e-open','E2E pouze minimální míra','CZK',2500,5000000);

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

-- Source text intentionally retained as-is: date-only and malformed values must not
-- be silently treated as verified application deadlines by the detail UI.
INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,starts_at,ends_at,description)
VALUES ('e2e-deadline-uncertain','gcv-e2e-unsafe-url','DOCUMENT_COMPLETION',
        '2027-06-01','datum-nejasne','Syntetický neověřený termín');

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
  ('gcv-e2e-unsafe-url','E2E výzva — bezpečnost odkazu',
   'Syntetický poškozený odkaz pouze pro E2E test.',
   'bezpecnost odkazu','','bezpecnost odkazu','PLANNED',NULL,'2026-09-26T20:00:00Z'),
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

-- OPEN non-grant sentinel: the project CTA must not promise a grant or eligibility.
UPDATE grant_call_versions SET funding_instrument_type='LOAN' WHERE id='gcv-e2e-page-24';
INSERT INTO funding_scenarios(id,grant_call_version_id,name,instrument_type,currency_code)
VALUES ('e2e-funding-open-loan','gcv-e2e-page-24','E2E otevřený úvěr','LOAN','CZK');

WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 25)
INSERT INTO source_records(id,source_id,external_id,canonical_url,record_type,grant_call_id,
  first_seen_at,last_seen_at,presence_state,missing_run_count,content_hash)
SELECT 'e2e-sr-page-' || i,'e2e-source-open','E2E-PAGE-' || i,
  'https://example.invalid/e2e/page/' || i,'GRANT_CALL','grant:e2e:page:' || i,
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z','SEEN',0,printf('%064d',i) FROM n;

-- Synthetic presence boundaries for grant detail; canonical OPEN status stays unchanged.
UPDATE source_records SET presence_state='MISSING_CANDIDATE',missing_run_count=1
WHERE id='e2e-sr-page-21';
UPDATE source_records SET presence_state='CONFIRMED_MISSING',missing_run_count=3
WHERE id='e2e-sr-page-22';
UPDATE source_records SET presence_state='MISSING_CANDIDATE',missing_run_count=1
WHERE id='e2e-sr-page-23';
INSERT INTO source_records(id,source_id,external_id,canonical_url,record_type,grant_call_id,
  first_seen_at,last_seen_at,presence_state,missing_run_count,content_hash)
VALUES ('e2e-sr-page-23-seen','e2e-source-planned','E2E-PAGE-23-B',
  'https://example.invalid/e2e/page/23-b','GRANT_CALL','grant:e2e:page:23',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z','SEEN',0,printf('%064d',123));
-- Lexical order reverses chronological order across these source timezone offsets.
UPDATE source_records SET last_seen_at='2026-10-01T23:30:00-10:00'
WHERE id='e2e-sr-page-23';
UPDATE source_records SET last_seen_at='2026-10-02T00:30:00+14:00'
WHERE id='e2e-sr-page-23-seen';
UPDATE source_records SET last_seen_at='2026-02-30T12:00:00Z'
WHERE id='e2e-sr-page-20';
DELETE FROM source_records WHERE id='e2e-sr-page-24';

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
  'e2e-date-' || kind,NULL,'OPEN',CASE WHEN kind = 'offset' THEN 'E2E offset výzva' ELSE 'E2E date ' || kind END,
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z'
FROM (SELECT 'only' AS kind UNION ALL SELECT 'invalid' UNION ALL SELECT 'malformed' UNION ALL SELECT 'null'
  UNION ALL SELECT 'offset');

INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  submission_close_at,official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-date-' || kind,'grant:e2e:date:' || kind,1,'2026-09-26T20:00:00Z',
  CASE WHEN kind = 'offset' THEN 'E2E offset výzva' ELSE 'E2E date ' || kind END,
  CASE WHEN kind = 'offset' THEN 'offsetonlyfixture' ELSE 'date-boundary fixture' END,'OPEN',close_at,
  CASE WHEN kind = 'only' THEN NULL ELSE 'https://example.invalid/e2e/date/' || kind END,
  'CZK','e2e-v1',printf('%064d',100 + ordinal),
  'VERIFIED','2026-09-26T20:00:00Z'
FROM (SELECT 'only' AS kind,'2027-05-01' AS close_at,1 AS ordinal
  UNION ALL SELECT 'invalid','2027-02-30',2
  UNION ALL SELECT 'malformed','not-a-date',3
  UNION ALL SELECT 'null',NULL,4
  UNION ALL SELECT 'offset','2027-05-01T16:30:45+02:00',5);

UPDATE grant_calls SET current_version_id = 'gcv-e2e-date-' || substr(id, length('grant:e2e:date:') + 1)
WHERE id LIKE 'grant:e2e:date:%';

INSERT INTO grant_search_documents(grant_call_version_id,title,summary,supported_activities,
  eligible_costs,keywords,status,submission_close_at,updated_at)
SELECT id,title,summary,CASE WHEN id = 'gcv-e2e-date-offset' THEN 'offsetonlyfixture' ELSE 'date-boundary' END,
  '',CASE WHEN id = 'gcv-e2e-date-offset' THEN 'offsetonlyfixture' ELSE 'date-boundary' END,status,submission_close_at,
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

-- SQLite accepts 24:00:00Z as the preceding calendar date for bounded filters.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
VALUES ('grant:e2e:endofday','e2e-programme-open','E2E-ENDOFDAY','e2e-endofday',NULL,
  'OPEN','E2E end-of-day výzva','2026-09-26T20:00:00Z','2026-09-26T20:00:00Z',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z');
INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  submission_close_at,official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
VALUES ('gcv-e2e-endofday','grant:e2e:endofday',1,'2026-09-26T20:00:00Z',
  'E2E end-of-day výzva','endofday-boundary fixture','OPEN','2027-05-01T24:00:00Z',NULL,
  'CZK','e2e-v1',printf('%064d',220),'VERIFIED','2026-09-26T20:00:00Z');
UPDATE grant_calls SET current_version_id='gcv-e2e-endofday' WHERE id='grant:e2e:endofday';
INSERT INTO grant_search_documents(grant_call_version_id,title,summary,supported_activities,
  eligible_costs,keywords,status,submission_close_at,updated_at)
VALUES ('gcv-e2e-endofday','E2E end-of-day výzva','endofday-boundary fixture',
  'endofday-boundary','','endofday-boundary','OPEN','2027-05-01T24:00:00Z','2026-09-26T20:00:00Z');

-- Lowercase UTC suffix is accepted by SQLite's bounded date expression.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
VALUES ('grant:e2e:lowerz','e2e-programme-open','E2E-LOWERZ','e2e-lowerz',NULL,
  'OPEN','E2E lowercase UTC výzva','2026-09-26T20:00:00Z','2026-09-26T20:00:00Z',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z');
INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  submission_close_at,official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
VALUES ('gcv-e2e-lowerz','grant:e2e:lowerz',1,'2026-09-26T20:00:00Z',
  'E2E lowercase UTC výzva','lowerz-boundary fixture','OPEN','2027-05-01T12:00:00z',NULL,
  'CZK','e2e-v1',printf('%064d',221),'VERIFIED','2026-09-26T20:00:00Z');
UPDATE grant_calls SET current_version_id='gcv-e2e-lowerz' WHERE id='grant:e2e:lowerz';
INSERT INTO grant_search_documents(grant_call_version_id,title,summary,supported_activities,
  eligible_costs,keywords,status,submission_close_at,updated_at)
VALUES ('gcv-e2e-lowerz','E2E lowercase UTC výzva','lowerz-boundary fixture',
  'lowerz-boundary','','lowerz-boundary','OPEN','2027-05-01T12:00:00z','2026-09-26T20:00:00Z');

-- Canonical status boundaries for detail actions; no source-record disappearance is involved.
INSERT INTO providers(id,name,provider_type,official_url)
VALUES ('e2e-provider-no-url','E2E provider bez odkazu','NATIONAL',NULL);
INSERT INTO programmes(id,provider_id,name,funding_origin,official_url)
VALUES ('e2e-programme-no-url','e2e-provider-no-url','E2E program bez odkazu','CZ_NATIONAL',NULL);
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
SELECT 'grant:e2e:status:' || lower(status),
  CASE WHEN status='ARCHIVED' THEN 'e2e-programme-no-url' ELSE programme_id END,
  'E2E-STATUS-' || status,
  'e2e-status-' || lower(status),NULL,status,'E2E stav ' || status,
  first_seen_at,first_published_at,created_at,updated_at
FROM grant_calls JOIN (SELECT 'PAUSED' AS status UNION ALL SELECT 'CLOSED' UNION ALL SELECT 'CANCELLED'
  UNION ALL SELECT 'ANNOUNCED' UNION ALL SELECT 'ARCHIVED') ON id='grant:e2e:page:20';

INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-status-' || lower(current_status),id,1,'2026-09-26T20:00:00Z',current_title,
  'Testovací kanonický stav.',current_status,
  CASE WHEN current_status='ARCHIVED' THEN NULL ELSE 'https://example.invalid/e2e/status/' || lower(current_status) END,
  'CZK','e2e-v1',printf('%064d',300 + CASE current_status WHEN 'PAUSED' THEN 1 WHEN 'CLOSED' THEN 2
    WHEN 'CANCELLED' THEN 3 WHEN 'ANNOUNCED' THEN 4 ELSE 5 END),
  'VERIFIED','2026-09-26T20:00:00Z' FROM grant_calls WHERE id LIKE 'grant:e2e:status:%';

UPDATE grant_calls SET current_version_id='gcv-e2e-status-' || lower(current_status)
WHERE id LIKE 'grant:e2e:status:%';

-- More than the detail API's 100-row evidence cap, tied to the same synthetic call.
INSERT INTO source_documents(id,grant_call_id,source_id,document_type,title,source_url,first_seen_at,last_seen_at)
VALUES ('e2e-doc-page-21','grant:e2e:page:21','e2e-source-open','CALL_DOCUMENT',
  'E2E doklady stránkování','https://example.invalid/e2e/page/21-evidence',
  '2026-09-26T20:00:00Z','2026-09-26T20:00:00Z');
INSERT INTO document_versions(id,source_document_id,sha256,retrieved_at,mime_type,file_size,object_key,
  parser_version,extraction_status,page_count,language_code)
VALUES ('e2e-dv-page-21','e2e-doc-page-21',printf('%064d',321),
  '2026-09-26T20:00:00Z','application/pdf',128,'raw/E2E/e2e-page-21.pdf',
  'e2e-v1','EXTRACTED',101,'cs');
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 101)
INSERT INTO field_evidence(id,entity_type,entity_id,field_path,document_version_id,
  page_from,page_to,evidence_text,extraction_method,extractor_version,
  confidence_ppm,verification_status,created_at)
SELECT 'e2e-fe-page-21-' || printf('%03d',i),'GRANT_CALL_VERSION','gcv-e2e-page-21',
  '/synthetic/' || i,'e2e-dv-page-21',i,i,'Synthetic E2E evidence ' || i,
  'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z' FROM n;

-- Detail items reference row 101, which the bounded API evidence list omits.
-- Paired NULL references keep the distinct "not attached" state covered.
INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,ends_at,timezone,description,evidence_id)
VALUES ('e2e-deadline-page-21-referenced','gcv-e2e-page-21','PROJECT_FINISH',
        '2027-12-31T23:59:59Z','UTC','E2E termín s odkazem na doklad 101','e2e-fe-page-21-101'),
       ('e2e-deadline-page-21-unattached','gcv-e2e-page-21','DOCUMENT_COMPLETION',
        '2027-11-30T23:59:59Z','UTC','E2E termín bez dokladu',NULL);
INSERT INTO funding_scenarios(id,grant_call_version_id,name,currency_code,evidence_id)
VALUES ('e2e-funding-page-21-referenced','gcv-e2e-page-21','E2E finance s odkazem na doklad 101','CZK','e2e-fe-page-21-101'),
       ('e2e-funding-page-21-unattached','gcv-e2e-page-21','E2E finance bez dokladu','CZK',NULL);
INSERT INTO grant_requirements(id,grant_call_version_id,requirement_type,title,necessity,evidence_id)
VALUES ('e2e-req-page-21-referenced','gcv-e2e-page-21','ACTION','E2E požadavek s odkazem na doklad 101','REQUIRED','e2e-fe-page-21-101'),
       ('e2e-req-page-21-unattached','gcv-e2e-page-21','ACTION','E2E požadavek bez dokladu','REQUIRED',NULL);

-- Isolated 22-version synthetic call: only 20 versions can appear in Detail API.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
VALUES ('grant:e2e:history','e2e-programme-open','E2E-HISTORY','e2e-history',NULL,
  'OPEN','E2E historie verzí','2026-09-01T20:00:00Z','2026-09-01T20:00:00Z',
  '2026-09-01T20:00:00Z','2026-09-26T20:00:00Z');
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 22)
INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-history-' || i,'grant:e2e:history',i,
  '2026-09-26T20:00:00Z','E2E historie verzí',
  'Syntetické verze pouze pro ověření omezení historie.', 'OPEN',
  'https://example.invalid/e2e/history','CZK','e2e-v1',printf('%064d',500 + i),
  'VERIFIED','2026-09-26T20:00:00Z' FROM n;
UPDATE grant_calls SET current_version_id='gcv-e2e-history-22'
WHERE id='grant:e2e:history';

-- Previously published content reactivated after 22 immutable versions. The
-- current pointer can legitimately refer to a version outside the newest 20.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
VALUES ('grant:e2e:reactivated','e2e-programme-open','E2E-REACTIVATED','e2e-reactivated',NULL,
  'OPEN','E2E reaktivovaná verze','2026-09-01T20:00:00Z','2026-09-01T20:00:00Z',
  '2026-09-01T20:00:00Z','2026-09-26T20:00:00Z');
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 22)
INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
SELECT 'gcv-e2e-reactivated-' || i,'grant:e2e:reactivated',i,
  '2026-09-26T20:00:00Z','E2E reaktivovaná verze',
  'Syntetická reaktivace dřívější neměnné verze.', 'OPEN',
  'https://example.invalid/e2e/reactivated','CZK','e2e-v1',printf('%064d',600 + i),
  'VERIFIED','2026-09-26T20:00:00Z' FROM n;
UPDATE grant_calls SET current_version_id='gcv-e2e-reactivated-1'
WHERE id='grant:e2e:reactivated';

-- Detail source and change limits: the 21st source is SEEN but sorts after 20 missing records.
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 21)
INSERT INTO source_records(id,source_id,external_id,canonical_url,record_type,grant_call_id,
  first_seen_at,last_seen_at,presence_state,missing_run_count)
SELECT 'e2e-sr-history-' || printf('%02d',i),'e2e-source-open',
  'E2E-HISTORY-' || printf('%02d',i),
  'https://example.invalid/e2e/history/source/' || i,'GRANT_CALL','grant:e2e:history',
  '2026-09-01T20:00:00Z',
  CASE WHEN i = 21 THEN '2026-09-23T00:00:00Z' ELSE printf('2026-09-25T%02d:00:00Z',i) END,
  CASE WHEN i = 21 THEN 'SEEN' ELSE 'CONFIRMED_MISSING' END,
  CASE WHEN i = 21 THEN 0 ELSE 3 END FROM n;

WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 21)
INSERT INTO change_events(id,grant_call_id,from_version_id,to_version_id,change_type,
  severity,field_path,created_at)
SELECT 'e2e-change-history-' || printf('%02d',i),'grant:e2e:history',
  'gcv-e2e-history-21','gcv-e2e-history-22','OTHER','INFORMATIONAL',
  '/e2e/history/change/' || printf('%02d',i),
  printf('2026-09-26T%02d:00:00Z',i) FROM n;

-- A malformed event timestamp must not become an apparently verified change date.
INSERT INTO change_events(id,grant_call_id,from_version_id,to_version_id,change_type,
  severity,field_path,created_at)
VALUES ('e2e-change-unverified-date','grant:e2e:reactivated',
  'gcv-e2e-reactivated-21','gcv-e2e-reactivated-22','OTHER','CRITICAL',
  '/e2e/unverified-date','2026-02-30T12:00:00Z');

-- Isolated zero-decimal currency: the UI must not divide JPY minor units by 100.
INSERT INTO grant_calls(id,programme_id,canonical_code,canonical_slug,current_version_id,
  current_status,current_title,first_seen_at,first_published_at,created_at,updated_at)
VALUES ('grant:e2e:jpy','e2e-programme-open','E2E-JPY','e2e-jpy',NULL,
  'PLANNED','E2E měnová přesnost JPY','2026-09-20T08:00:00Z','2026-09-20T08:00:00Z',
  '2026-09-20T08:00:00Z','2026-09-26T20:00:00Z');
INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,summary,status,
  official_detail_url,currency_code,normalization_version,content_hash,verification_status,created_at)
VALUES ('gcv-e2e-jpy','grant:e2e:jpy',1,'2026-09-26T20:00:00Z',
  'E2E měnová přesnost JPY','Syntetická výzva pouze pro ověření měnového zobrazení.',
  'PLANNED','https://example.invalid/e2e/jpy','JPY','e2e-v1',
  'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
  'NEEDS_REVIEW','2026-09-26T20:00:00Z');
UPDATE grant_calls SET current_version_id='gcv-e2e-jpy' WHERE id='grant:e2e:jpy';
INSERT INTO source_records(id,source_id,external_id,canonical_url,record_type,grant_call_id,
  first_seen_at,last_seen_at,presence_state,missing_run_count)
VALUES ('e2e-sr-jpy','e2e-source-open','E2E-JPY','https://example.invalid/e2e/jpy',
  'GRANT_CALL','grant:e2e:jpy','2026-09-20T08:00:00Z','2026-09-26T20:00:00Z','SEEN',0);
INSERT INTO funding_scenarios(id,grant_call_version_id,name,currency_code,grant_amount_max_minor)
VALUES ('e2e-funding-jpy','gcv-e2e-jpy','E2E JPY scénář','JPY',1234);
