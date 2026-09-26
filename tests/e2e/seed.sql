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
   'GRANT_CALL','grant:e2e:open','2026-09-20T08:00:00Z','2026-09-26T20:00:00Z','SEEN',0,
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
   'E2E_SEED','e2e-v1',1000000,'VERIFIED','2026-09-26T20:00:00Z');

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
