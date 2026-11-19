// @ts-nocheck -- mirrors the existing Miniflare D1 fixture until Node test types are configured.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import type { Env } from "../src/env";
import { handleRequest } from "../src/index";
import { hashOwnerToken } from "../src/projectAccess";

const token = "A".repeat(43);
const other = "B".repeat(43);
const now = "2026-01-01T00:00:00Z";
const grant = "grant-1";
let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

async function setup(): Promise<Env> {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "eligibility-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "eligibility-test" },
  }));
  const db = await mf.getD1Database("DB");
  const migrations = resolve(import.meta.dirname, "../../../migrations");
  for (const file of ["0001_core_identity.sql", "0002_documents_provenance.sql", "0003_funding_projects_changes.sql",
    "0006_eligibility_rules.sql", "0007_applicant_profiles.sql", "0017_project_sharing.sql",
    "0018_project_owner_capabilities.sql", "0023_geography_applicant_rules.sql", "0029_applicant_profile_owner_identity.sql",
    "0030_applicant_sparse_ico_invalidation.sql"]) {
    const sql = readFileSync(resolve(migrations, file), "utf8")
      .replace(/^\s*--[^\n]*$/gm, "").replace(/^PRAGMA foreign_keys = ON;\s*/gm, "").replace(/\r?\n/g, " ");
    if (file.startsWith("0030_")) { await db.exec(sql); continue; }
    for (const statement of sql.split(";").map((part: string) => part.trim()).filter(Boolean)) await db.prepare(statement).run();
  }
  await db.prepare("INSERT INTO providers(id,name,provider_type) VALUES ('provider','Provider','NATIONAL')").run();
  await db.prepare("INSERT INTO programmes(id,provider_id,name,funding_origin) VALUES ('program','provider','Program','CZ_NATIONAL')").run();
  await db.prepare(`INSERT INTO source_registry(id,code,name,base_url,adapter_key,authority,retrieval_mode,refresh_minutes)
    VALUES ('source','SOURCE','Source','https://example.test','fixture','OFFICIAL','HTTP',60)`).run();
  await db.prepare(`INSERT INTO source_documents(id,source_id,document_type,source_url,first_seen_at)
    VALUES ('document','source','CALL_DOCUMENT','https://example.test/document',?)`).bind(now).run();
  await db.prepare(`INSERT INTO document_versions(id,source_document_id,sha256,retrieved_at,mime_type,object_key,extraction_status)
    VALUES ('document-version','document','hash',?,'text/plain','test','EXTRACTED')`).bind(now).run();
  await db.prepare(`INSERT INTO field_evidence(id,entity_type,entity_id,field_path,document_version_id,verification_status,created_at)
    VALUES ('evidence-rule','GRANT_CALL_VERSION','v1','eligibility','document-version','VERIFIED',?)`).bind(now).run();
  await db.prepare(`INSERT INTO grant_calls(id,programme_id,canonical_slug,current_version_id,current_status,current_title,first_seen_at,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?)`).bind(grant, "program", "grant-1", "v1", "OPEN", "Grant", now, now, now).run();
  await db.prepare(`INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at)
    VALUES (?,?,?,?,?,?,?,?)`).bind("v1", grant, 1, now, "Grant", "OPEN", "VERIFIED", now).run();
  for (const [id, capability] of [["prj_" + "a".repeat(32), token], ["prj_" + "b".repeat(32), other]]) {
    await db.prepare(`INSERT INTO projects(id,owner_user_id,natural_language_intent,currency_code,created_at,updated_at)
      VALUES (?,?,?,?,?,?)`).bind(id, `anonymous:${id}`, "test", "CZK", now, now).run();
    await db.prepare("INSERT INTO project_owner_capabilities(project_id,token_hash,created_at) VALUES (?,?,?)")
      .bind(id, await hashOwnerToken(capability), now).run();
  }
  return { DB: db as unknown as Env["DB"], RAW: { async head() { return null; } },
    SEARCH: { async describe() { return {}; } }, ENVIRONMENT: "local" };
}
async function seedRule(env: Env, version = "v1", op = "EQ", expected = '"MUNICIPALITY"'): Promise<void> {
  await env.DB.prepare(`INSERT INTO eligibility_rule_sets(id,grant_call_version_id,name,completeness_status,verification_status)
    VALUES (?,?,?,?,?)`).bind(`rs-${version}`, version, "Applicant", "COMPLETE", "VERIFIED").run();
  await env.DB.prepare("INSERT INTO rule_groups(id,rule_set_id,group_operator) VALUES (?,?,?)")
    .bind(`root-${version}`, `rs-${version}`, "AND").run();
  await env.DB.prepare(`INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,expected_value_json,verification_status,evidence_id)
    VALUES (?,?,?,?,?,?,?)`).bind(`type-${version}`, `root-${version}`, "attr-applicant-type", op, expected, "VERIFIED", "evidence-rule").run();
}
function req(capability?: string): Request {
  return new Request(`https://example.test/grants/${grant}/eligibility`,
    { headers: capability ? { authorization: `Bearer ${capability}` } : {} });
}
async function result(env: Env, capability = token): Promise<Record<string, any>> {
  const response = await handleRequest(req(capability), env);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  return await response.json() as Record<string, any>;
}

describe("eligibility endpoint with real D1", () => {
  it("recomputes UNKNOWN after a profile answer, then failure, without exposing values", async () => {
    const env = await setup();
    await seedRule(env);
    const initial = await result(env);
    expect(initial).toMatchObject({ status: "NEEDS_INFORMATION", rootResult: "UNKNOWN", versionId: "v1", ruleSetId: "rs-v1", missingAttributes: ["applicant.type"] });
    expect(initial.conditions[0]).toMatchObject({ conditionId: "type-v1", evidenceId: "evidence-rule", result: "UNKNOWN", reason: "MISSING_INPUT" });
    const put = async (applicantType: string) => handleRequest(new Request("https://example.test/applicant-profile", {
      method: "PUT", headers: { authorization: `Bearer ${token}` }, body: JSON.stringify({ applicantType }),
    }), env);
    expect((await put("MUNICIPALITY")).status).toBe(200);
    expect(await result(env)).toMatchObject({ status: "LIKELY_ELIGIBLE", rootResult: "PASS", missingAttributes: [] });
    expect((await put("BUSINESS")).status).toBe(200);
    const failed = await result(env);
    expect(failed).toMatchObject({ status: "NEEDS_REVIEW", rootResult: "FAIL", blockers: ["type-v1"] });
    expect(JSON.stringify(failed)).not.toContain("MUNICIPALITY");
    expect(JSON.stringify(failed)).not.toContain("BUSINESS");
  });

  it("hides invalid capability and another owner's profile", async () => {
    const env = await setup(); await seedRule(env);
    for (const capability of [undefined, "X".repeat(43)]) {
      const response = await handleRequest(req(capability), env);
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: "OWNER_CAPABILITY_INVALID" });
    }
    await env.DB.prepare(`INSERT INTO applicant_profiles(id,user_id,applicant_type,created_at,updated_at)
      VALUES ('profile-other',?,?,?,?)`).bind(`anonymous:prj_${"b".repeat(32)}`, "MUNICIPALITY", now, now).run();
    expect((await result(env)).status).toBe("NEEDS_INFORMATION");
    expect((await result(env, other)).status).toBe("LIKELY_ELIGIBLE");
    await env.DB.prepare("UPDATE project_owner_capabilities SET revoked_at = ? WHERE token_hash = ?")
      .bind(now, await hashOwnerToken(other)).run();
    expect((await handleRequest(req(other), env)).status).toBe(404);
  });

  it("uses the current version and fails closed for missing or unsupported rules", async () => {
    const env = await setup(); await seedRule(env);
    await env.DB.prepare(`INSERT INTO applicant_profiles(id,user_id,applicant_type,created_at,updated_at)
      VALUES ('profile-a',?,?,?,?)`).bind(`anonymous:prj_${"a".repeat(32)}`, "MUNICIPALITY", now, now).run();
    expect((await result(env)).status).toBe("LIKELY_ELIGIBLE");
    await env.DB.prepare(`INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at)
      VALUES (?,?,?,?,?,?,?,?)`).bind("v2", grant, 2, now, "Grant", "OPEN", "VERIFIED", now).run();
    await env.DB.prepare("UPDATE grant_calls SET current_version_id = 'v2' WHERE id = ?").bind(grant).run();
    expect(await result(env)).toMatchObject({ versionId: "v2", ruleSetId: null, status: "NEEDS_REVIEW", reason: "NO_RULE_SET" });
    await seedRule(env, "v2", "GEO_WITHIN", '"geo-1"');
    expect(await result(env)).toMatchObject({ versionId: "v2", status: "NEEDS_REVIEW", rootResult: "ERROR" });
  });

  it("reads fresh applicant inputs across real D1 batches", async () => {
    const env = await setup(); await seedRule(env);
    expect(await result(env)).toMatchObject({ versionId: "v1", status: "NEEDS_INFORMATION" });
    await env.DB.prepare(`INSERT INTO applicant_profiles(id,user_id,applicant_type,created_at,updated_at)
      VALUES ('profile-a',?,?,?,?)`).bind(`anonymous:prj_${"a".repeat(32)}`, "MUNICIPALITY", now, now).run();
    expect(await result(env)).toMatchObject({ versionId: "v1", status: "LIKELY_ELIGIBLE" });
  });

  it("uses verified sparse legal form when the mapped column is null, with column precedence when present", async () => {
    const env = await setup(); await seedRule(env);
    await env.DB.prepare(`INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,
      expected_value_json,unknown_policy,verification_status,evidence_id,sort_order)
      VALUES ('legal','root-v1','attr-applicant-legal-form','EQ','"GOOD"','NOT_APPLICABLE','VERIFIED','evidence-rule',1)`).run();
    await env.DB.prepare(`INSERT INTO applicant_profiles(id,user_id,applicant_type,legal_form_code,created_at,updated_at)
      VALUES ('profile-a',?,'MUNICIPALITY',NULL,?,?)`)
      .bind(`anonymous:prj_${"a".repeat(32)}`, now, now).run();
    await env.DB.prepare(`INSERT INTO applicant_attribute_values(id,applicant_profile_id,attribute_definition_id,
      value_type,value_json,source_kind,observed_at,verification_status,evidence_id)
      VALUES ('legal-value','profile-a','attr-applicant-legal-form','STRING','"BAD"','ARES',?,'VERIFIED','evidence-rule')`)
      .bind(now).run();
    expect(await result(env)).toMatchObject({ status: "INELIGIBLE", rootResult: "FAIL", blockers: ["legal"],
      conditions: [{ conditionId: "type-v1", result: "PASS" }, { conditionId: "legal", result: "FAIL",
        inputSource: "ATTRIBUTE_VALUE", inputVerification: "VERIFIED", inputEvidenceId: "evidence-rule" }] });
    await env.DB.prepare("UPDATE applicant_profiles SET legal_form_code = 'GOOD' WHERE id = 'profile-a'").run();
    expect(await result(env)).toMatchObject({ status: "LIKELY_ELIGIBLE", rootResult: "PASS",
      conditions: [{ result: "PASS" }, { result: "PASS", inputSource: "PROFILE" }] });
    await env.DB.prepare("UPDATE applicant_profiles SET legal_form_code = 'UNKNOWN' WHERE id = 'profile-a'").run();
    expect(await result(env)).toMatchObject({ status: "INELIGIBLE", rootResult: "FAIL",
      conditions: [{ result: "PASS" }, { result: "FAIL", inputSource: "ATTRIBUTE_VALUE" }] });
  });

  it("invalidates verified sparse facts atomically when the owner changes IČO", async () => {
    const env = await setup(); await seedRule(env);
    await env.DB.prepare(`INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,
      expected_value_json,verification_status,evidence_id,sort_order)
      VALUES ('legal','root-v1','attr-applicant-legal-form','EQ','"GOOD"','VERIFIED','evidence-rule',1)`).run();
    await env.DB.prepare(`INSERT INTO applicant_profiles(id,user_id,applicant_type,ico,created_at,updated_at)
      VALUES ('profile-a',?,'MUNICIPALITY','12345678',?,?)`)
      .bind(`anonymous:prj_${"a".repeat(32)}`, now, now).run();
    await env.DB.prepare(`INSERT INTO applicant_attribute_values(id,applicant_profile_id,attribute_definition_id,
      value_type,value_json,source_kind,observed_at,verified_at,verification_status,evidence_id)
      VALUES ('legal-value','profile-a','attr-applicant-legal-form','STRING','"BAD"','ARES',?,?,'VERIFIED','evidence-rule')`)
      .bind(now, now).run();
    expect(await result(env)).toMatchObject({ status: "INELIGIBLE", rootResult: "FAIL", blockers: ["legal"] });
    const response = await handleRequest(new Request("https://example.test/applicant-profile", {
      method: "PUT", headers: { authorization: `Bearer ${token}` },
      body: JSON.stringify({ applicantType: "MUNICIPALITY", ico: "87654321" }),
    }), env);
    expect(response.status).toBe(200);
    expect(await result(env)).toMatchObject({ status: "NEEDS_REVIEW", rootResult: "FAIL", blockers: ["legal"],
      conditions: [{ inputVerification: "USER_DECLARED" }, { inputVerification: "NEEDS_REVIEW" }] });
    const sparse = await env.DB.prepare("SELECT verification_status, verified_at FROM applicant_attribute_values WHERE id = 'legal-value'").first();
    expect(sparse).toMatchObject({ verification_status: "NEEDS_REVIEW", verified_at: null });
    const otherProject = await env.DB.prepare("SELECT natural_language_intent FROM projects WHERE id = ?")
      .bind("prj_" + "b".repeat(32)).first();
    expect(otherProject?.natural_language_intent).toBe("test");
  });
});
