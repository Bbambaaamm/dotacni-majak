# Production runbook

Issue: #41

Tento runbook je provozní podklad pro staging/production candidate. Neznamená,
že v1.0 gate již prošel.

## 1. První triage

Při incidentu nejdřív určete dopad:

- **SEV-1** — únik/změna citlivých dat, nesprávná autorizace, hromadná destrukce
  canonical dat, falešné kritické dotační tvrzení s širokým dopadem.
- **SEV-2** — hlavní search/workspace/API nefunguje, zdrojové pokrytí je významně
  omezené, ale integrita posledních ověřených dat zůstává.
- **SEV-3** — dílčí zdroj/funkce omezená, existuje bezpečný fallback.

Priorita je integrita a bezpečnost, ne dostupnost za každou cenu.

## 2. Zdroj/parser incident

Pokud se zlomí connector, parser nebo source page:

1. označit zdroj DEGRADED/UNAVAILABLE,
2. ponechat last-known-good canonical data,
3. zablokovat destructive reconciliation,
4. zkontrolovat RAW snapshot a SourceRun quality violations,
5. opravit parser na fixture/regression testu,
6. teprve potom reprocessnout RAW,
7. Source Health vrátit na HEALTHY až po úspěšném ověření.

Zmizení záznamu ze zdroje není důkaz CLOSED/CANCELLED.

## 3. Chybné canonical údaje

1. zastavit publikaci navazujících notifications/reindex eventů, pokud mohou šířit chybu,
2. identifikovat GrantCallVersion + provenance,
3. nepřepisovat historický immutable snapshot,
4. publikovat novou opravenou verzi s audit trail,
5. vyvolat change/watch reevaluation,
6. pokud chybná informace mohla ovlivnit uživatele, připravit incident notice.

## 4. API / Worker incident

Kontrola:
- `/health`
- `/ready`
- release SHA
- D1 binding/read
- poslední deployment/version

Rollback Workeru používejte podle `docs/DEPLOYMENT_CLOUDFLARE.md`.

Rollback Workeru **nevrací D1/R2/Vectorize data**. Nikdy tedy neprovádět rollback
kódu přes nekompatibilní DB migration bez recovery plánu.

## 5. D1 recovery

Před destruktivním zásahem:
- exportovat aktuální stav,
- zaznamenat release SHA + migration level,
- ověřit scope poškození,
- preferovat forward-fix migration před ručním přepisem.

Release gate vyžaduje samostatný tabletop/restore rehearsal s konkrétní evidencí.
Secrets ani produkční dumpy se necommitují do repozitáře.

## 6. R2 RAW recovery

RAW snapshoty jsou immutable/content-addressed. Při poškození downstream dat:
- ověřit SHA-256,
- znovu spustit parser/extractor nad existujícím RAW,
- nestahovat stejný externí obsah bez potřeby.

Chybějící/poškozený RAW u kritického zdroje je data-quality incident.

## 7. Vector/Search incident

Vectorize není source of truth.

Při výpadku nebo vyčerpání budgetu:
- vypnout semantic retrieval,
- použít FTS + ontology + structured filters,
- canonical data a eligibility zůstávají funkční,
- veřejně nekomunikovat relevance jako eligibility.

Index lze znovu vystavět z canonical SearchProfile.

## 8. Outbox / notification incident

Outbox je at-least-once:
- FAILED/PENDING eventy lze retry,
- handler musí být idempotentní,
- dedupe_key zabraňuje duplicitnímu logickému eventu.

Před hromadným replay notifications nejdřív ověřit, že původní příčina byla
opravena a že replay neposílá zastaralé informace.

## 9. Share/owner capability incident

Při podezření na kompromitaci:
- revokovat/rotovat owner capability konkrétního projektu,
- revokovat relevantní share links,
- raw tokeny nikdy nelogovat,
- neodhalovat existenci projektu podle invalid tokenu.

Share link je read-only; jakýkoli write přes share token je SEV-1.

## 10. Free-tier / cost incident

Nikdy nezapínat placený tarif automaticky.

Při překročení budget threshold:
1. cache/batch/index optimalizace,
2. nižší refresh cadence neurgentních zdrojů,
3. semantic fallback,
4. dočasné omezení náročné vedlejší funkce,
5. transparentní status, pokud je uživatelský dopad.

## 11. Security incident

- omezit/odstavit zasaženou cestu,
- zachovat potřebné audit logy bez raw secrets,
- rotovat secrets/capabilities podle scope,
- nevkládat exploit detail do veřejného issue před opravou,
- po fixu přidat regression test,
- provést incident review.

## 12. Release rollback checklist

- [ ] určit poslední známou dobrou Worker verzi
- [ ] ověřit DB migration kompatibilitu
- [ ] rollback/upload/deploy podle Cloudflare postupu
- [ ] ověřit /health a /ready
- [ ] smoke test search + detail + source
- [ ] ověřit project/share autorizaci
- [ ] ověřit Source Health
- [ ] zaznamenat incident/release SHA

## 13. Recovery tabletop před v1.0

Bez produkčních dat/secrets simulovat minimálně:
- rozbitý parser → last-known-good,
- chybný release Workeru → rollback,
- výpadek Vectorize → FTS fallback,
- failed outbox event → safe retry,
- kompromitovaný share link → revoke,
- DB restore/export scénář.

Každý scénář musí mít datum, účastníka/reviewer, výsledek a follow-up findings.
