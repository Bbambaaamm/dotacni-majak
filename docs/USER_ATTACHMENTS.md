# User Document Attachments — M12 private storage model

Status: implemented (slice 1/?) · 2026-09-30

## Purpose
Volitelné ukládání uživatelských příloh v rámci pracovního prostoru (workspace), s explicitním oddělením od oficiálních dokumentů zdrojů a s definovanými limity, oprávněním a záznamem.

Tento dokument pokrývá pouze **uživatelsky vytvořené přílohy** (dokumenty, které uživatel nahrál k projektu/úloze). Oficiální dokumenty poskytovatelů se nezmění a nejsou součástí tohoto modelu.

## Scope (what is in)
- Prázdný model: tabulka `user_document_attachments` s vlastnictvím, klíčem do soukromého R2, MIME/size limity, stavem, audit záznamy.
- API: POST /projects/{id}/attachments, GET /projects/{id}/attachments/{id}, DELETE /projects/{id}/attachments/{id}.
- Oprávnění: pouze owner capability (stejný model jako sdílení/watch). Žádná veřejná URL.
- Soukromé úložiště: oddělený R2 bucket přístupovaný jen přes Worker. Bytes nikam nejdou jako veřejné odkazy.

## Scope (what is out of this slice)
- Veřejné/readonly sdílení jednotlivých příloh (může přijít v separátním slice s vlastní capability + hash modelem).
- Převod/OCR/validace uvnitř souboru (soubor je uživatelský blob; pokud je potřeba parsovat, jde o jiný vrstevní krok).
- Plný account/login (používá se existující anonymní capability model z ADR-0007).
- UI upload komponenta a manuální a11y review (to je IP a mobile/accessibility stav dokumentován níže jako pending).

## Ownership / authorization (explicit)
- Vlastnictví je napojeno na existující `project_owner_capabilities` — kontrola proběhne proti `project_owner_capabilities.token_hash` pro daný projekt.
- Neplatný/udalený token → 404 `OWNER_CAPABILITY_INVALID` (non-disclosing, stejně jako sdílení/watch).
- Každá změna (vložení/smazání) vytváří audit řádek. Raw obsah souboru se nikam ne loguje.

## Metadata model
Tabulka `user_document_attachments`:
- `id` — stabilní identita
- `workspace_id` — vázána na workspace/projekt (projekt je skutečný vlastník javu; workspace je kontext)
- `owner_user_id` — vlastník (textový principal, stejně jako v projektu)
- `storage_key` — klíč do soukromého R2 bucketu; není veřejný URL, je to jen interní referencní pole.
- `filename` — původní název souboru (správné kódování, omezená délka)
- `mime_type` — omezená allowlist
- `size_bytes` — minor-unitless, omezeno
- `status` — UPLOADED / REJECTED / DELETED (DELETED = soft marker + skutečné zrušení R2 objektu)
- `created_at` / `updated_at`

## Storage
- Oddělený R2 bucket pro uživatelské přílohy (oddělení od RAW source snapshot bucketu).
- Až do budoucího provozu: objekty jsou dostupné jen přes Worker endpointy, které kontrolují owner capability. Žádný Cloudflare presigned URL ani veřejný read link v této fázi.
- Klíče v R2 jsou čisté/ regulované cesty (bez `..`, bez zástupných znaků mimo povolené), aby nedošlo k odposlání nebo přepsání cizích objektů.

## Limits
Aplikace enforceable limity (API layer):
- max velikost: 10 MB
- dovolené typy (MIME + rozšíření): PDF, PNG, JPEG, DOCX, XLSX/XLS, CSV, TXT
- žádné typy schématu/script/executable
- filename délka omezena, povolené znaky sanitizována

Tato omezení jsou méně přísná než ingestion RAW policy (dokumenty od poskytovatelů mohou být větší a složitější); uživatelské přílohy jsou jednodušší a dříve omezované kvůli UX a riziku.

## Official vs user/AI separation
- Oficiální dokumenty: `source_documents` / `document_versions` / `document_sections` / `field_evidence` — toto je canonical dokumentace zdroje, provenance, D1‑verzovaná.
- Uživatelské přílohy: `user_document_attachments` — vlastněné, soukromé, nejsou součástí canonical truth o dotaci.
- API endpointy pro uživatelské přílohy **ne dotýkají se** `document_versions` / `source_documents` — to je testováno.

## Privacy / retention
- Raw obsah souboru se nikdy nenachází v logu Workeru ani v API response (pouze metadata).
- DELETE je skutečné zrušení: DB řádek + R2 objekt + audit event.
- Revokace/odebrání je závazné a nemůže být pozpátě zveřejněno (žádná veřejná URL).
- Retention pro uživatelské přílohy je vlastně „delete = gone“; dlouhodobá retention policy je součástí obecné privacy architektury (#37), nikoliv přidáváme zde nové retention kategorie.

## Security / least privilege
- Pouze owner capability má přístup.
- R2 bucket je jen pro tento worker; žádné jiné služby/public access.
- Nedefaultujeme žádné sdílení.
- Audit události patří mezi zmíněné vlastnosti sdílení/watch modelu (CREATED, DELETED), raw token/content se neukládají.

## Tests
- Unit test pro čistou validaci vstupu (limits, MIME).
- Unit test pro module `attachmentAccess` (happy path, oprávnění, odmítnutí, audit).
- Route-level test v `index.test.ts` (owner capability guard, success path, chybové cesty, žádný leakage ofcial table access).
- Vše pomocí existujícího `Env` mock pattern (D1/R2/SEARCH).

## Paywall statement
Tento slice nezavádí žádnou platbu a žádnou new službu, která by mohla vést k paywallu pro core workflow. R2 je již součástí infrastruktury projektu; bucket je lokálně/simulován při testech stejně jako RAW.

## Mobile / accessibility stav (UI)
- Backend vrací JSON s `Cache-Control: private, no-store` pro metadata endpointy.
- Žádná veřejná URL → UI nemůže odkazovat na „pretty link“; komponenta uploadu bude muset komunikovat přes API (POST pro upload, GET pro metadu/listing).
- Manuální accessibility review upload flow (formulář, errorMessage, focus, načasované zprávy jako role=status, zoom/reflow) **není v tomto slice proveden** — pending UI slice. Backend v tomto směru nic neblokuje, ale UX a11y není tady dokončena.

## Dependents / done when
- Tento slice nedepenuje na nic novém; závislosti #37/#61 jsou v main (closed) a re-used.
- Sleduje se po merge, že tests projdou a že veřejné CI (pokud je dostupné) je zelené.
- Další slice může přidat: listing per workspace, přeposlání do workspace document context, podpora pro readonly share jednotlivých příloh (separátní capability).

## Known limitations
- Žádný download URL v tuto chvíli (pouze metadata + delete); pokud bude potřeba stahování příloh v UI, budou potřeba další endpointy/průvodce.
- Souborový obsíd nelze parsovat na úrovni tohoto modelu — je to jen blob.
