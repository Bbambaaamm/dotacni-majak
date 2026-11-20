// @ts-nocheck -- Miniflare D1 fixture follows the existing API integration-test convention.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import { verifyFinanceRuleProvenance } from "../src/financeProvenance";

let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

async function setup() {
  mf = new Miniflare(convertV4MiniflareOptions({ name: "finance-provenance-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "finance-provenance-test" } }));
  const db = await mf.getD1Database("DB");
  const migrations = resolve(import.meta.dirname, "../../../migrations");
  for (const file of ["0001_core_identity.sql", "0002_documents_provenance.sql",
    "0003_funding_projects_changes.sql", "0006_eligibility_rules.sql"]) {
    const sql = readFileSync(resolve(migrations, file), "utf8")
      .replace(/^\s*--[^\n]*$/gm, "").replace(/^PRAGMA foreign_keys = ON;\s*/gm, "").replace(/\r?\n/g, " ");
    for (const statement of sql.split(";").map((part: string) => part.trim()).filter(Boolean))
      await db.prepare(statement).run();
  }
  const statements = [
    "INSERT INTO providers(id,name,provider_type) VALUES ('provider','Provider','NATIONAL')",
    "INSERT INTO programmes(id,provider_id,name,funding_origin) VALUES ('programme','provider','Programme','CZ_NATIONAL')",
    "INSERT INTO grant_calls(id,programme_id,canonical_slug,current_version_id,current_status,current_title,first_seen_at,created_at,updated_at) VALUES ('call','programme','call','v1','OPEN','Call','2026','2026','2026')",
    "INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at) VALUES ('v1','call',1,'2026','Call','OPEN','VERIFIED','2026')",
    "INSERT INTO source_registry(id,code,name,base_url,adapter_key,authority,retrieval_mode,refresh_minutes) VALUES ('source','SRC','Source','https://example.test','fixture','OFFICIAL','HTTP',60)",
    "INSERT INTO source_documents(id,grant_call_id,source_id,document_type,source_url,first_seen_at) VALUES ('doc','call','source','CALL_DOCUMENT','https://example.test/doc','2026')",
    "INSERT INTO document_versions(id,source_document_id,sha256,retrieved_at,mime_type,object_key,extraction_status) VALUES ('dv','doc','hash','2026','text/plain','raw','EXTRACTED')",
    "INSERT INTO field_evidence(id,entity_type,entity_id,field_path,document_version_id,verification_status,created_at) VALUES ('rule-evidence','GRANT_CALL_VERSION','v1','/rule_conditions/c1','dv','VERIFIED','2026')",
    "INSERT INTO field_evidence(id,entity_type,entity_id,field_path,document_version_id,verification_status,created_at) VALUES ('scenario-evidence','GRANT_CALL_VERSION','v1','/funding_scenarios/s1','dv','VERIFIED','2026')",
    "INSERT INTO eligibility_rule_sets(id,grant_call_version_id,name,completeness_status,verification_status) VALUES ('rs','v1','Rules','COMPLETE','VERIFIED')",
    "INSERT INTO rule_groups(id,rule_set_id,group_operator) VALUES ('root','rs','AND')",
    "INSERT INTO rule_groups(id,rule_set_id,parent_group_id,group_operator) VALUES ('group','rs','root','AND')",
    "INSERT INTO attribute_definitions(id,attribute_key,scope,label_cs,data_type) VALUES ('attr','applicant.type','APPLICANT','Type','ENUM')",
    "INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,expected_value_json,verification_status,evidence_id) VALUES ('c1','group','attr','EQ','\"MUNICIPALITY\"','VERIFIED','rule-evidence')",
    "INSERT INTO funding_scenarios(id,grant_call_version_id,name,condition_group_id,currency_code,evidence_id) VALUES ('s1','v1','Scenario','group','CZK','scenario-evidence')",
  ];
  for (const statement of statements) await db.prepare(statement).run();
  return db;
}

const read = (db: any) => verifyFinanceRuleProvenance(db, "call");

describe("finance provenance on canonical D1", () => {
  it("proves current-version membership and exact official rule/scenario evidence without applicant values", async () => {
    const db = await setup();
    expect(await read(db)).toEqual({ status: "VERIFIED", reason: "VERSION_BOUND_OFFICIAL_EVIDENCE",
      versionId: "v1", ruleSetId: "rs", scenarioIds: ["s1"], conditionEvidenceIds: { c1: "rule-evidence" } });
    expect(await verifyFinanceRuleProvenance(db, "other")).toMatchObject({ status: "NEEDS_INFORMATION", reason: "NO_CURRENT_VERSION" });
    await db.prepare("INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at) VALUES ('v2','call',2,'2026','Call','OPEN','VERIFIED','2026')").run();
    await db.prepare("UPDATE grant_calls SET current_version_id='v2' WHERE id='call'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", versionId: "v2", reason: "RULE_SET_NOT_UNIQUE" });
  });

  it("rejects unrelated, unverified, nonofficial or quarantined evidence", async () => {
    const db = await setup();
    for (const [table, column, bad, good] of [
      ["field_evidence", "entity_id", "other-version", "v1"],
      ["field_evidence", "field_path", "/rule_conditions/other", "/rule_conditions/c1"],
      ["field_evidence", "entity_type", "OTHER", "GRANT_CALL_VERSION"],
      ["field_evidence", "verification_status", "NEEDS_REVIEW", "VERIFIED"],
      ["source_registry", "authority", "SECONDARY", "OFFICIAL"],
      ["document_versions", "extraction_status", "QUARANTINED", "EXTRACTED"],
      ["source_documents", "grant_call_id", null, "call"],
    ] as const) {
      const target = table === "field_evidence" ? " WHERE id='rule-evidence'" : "";
      await db.prepare(`UPDATE ${table} SET ${column}=?${target}`).bind(bad).run();
      expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNVERIFIED_OFFICIAL_EVIDENCE" });
      await db.prepare(`UPDATE ${table} SET ${column}=?${target}`).bind(good).run();
      expect((await read(db)).status).toBe("VERIFIED");
    }
    await db.prepare("UPDATE field_evidence SET field_path='/funding_scenarios/other' WHERE id='scenario-evidence'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNVERIFIED_OFFICIAL_EVIDENCE" });
  });

  it("fails closed on missing scenario groups, multiple sets and incomplete rules", async () => {
    const db = await setup();
    await db.prepare("UPDATE funding_scenarios SET condition_group_id=NULL WHERE id='s1'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "INCOMPLETE_RULE_GRAPH" });
    await db.prepare("UPDATE funding_scenarios SET condition_group_id='group' WHERE id='s1'").run();
    await db.prepare("UPDATE grant_call_versions SET verification_status='NEEDS_REVIEW' WHERE id='v1'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "GRANT_VERSION_UNVERIFIED" });
    await db.prepare("UPDATE grant_call_versions SET verification_status='VERIFIED' WHERE id='v1'").run();
    await db.prepare("UPDATE rule_conditions SET rule_group_id='root' WHERE id='c1'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "INCOMPLETE_RULE_GRAPH" });
    await db.prepare("UPDATE rule_conditions SET rule_group_id='group' WHERE id='c1'").run();
    await db.prepare("UPDATE eligibility_rule_sets SET completeness_status='PARTIAL' WHERE id='rs'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "RULE_SET_UNVERIFIED" });
    await db.prepare("UPDATE eligibility_rule_sets SET completeness_status='COMPLETE' WHERE id='rs'").run();
    await db.prepare("INSERT INTO eligibility_rule_sets(id,grant_call_version_id,name,completeness_status,verification_status) VALUES ('rs2','v1','Other','COMPLETE','VERIFIED')").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "RULE_SET_NOT_UNIQUE" });
  });
  it("rejects rule trees the deterministic evaluator cannot traverse", async () => {
    const db = await setup();
    await db.prepare("INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,expected_value_json,verification_status,evidence_id) VALUES ('c2','root','attr','EQ','\"MUNICIPALITY\"','VERIFIED','rule-evidence')").run();
    await db.prepare("UPDATE rule_groups SET group_operator='NOT' WHERE id='root'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_GRAPH", scenarioIds: [] });
    await db.prepare("DELETE FROM rule_conditions WHERE id='c2'").run();
    await db.prepare("UPDATE rule_groups SET group_operator='AND' WHERE id='root'").run();
    await db.prepare("UPDATE rule_groups SET group_operator='NOT' WHERE id='group'").run();
    expect((await read(db)).status).toBe("VERIFIED");
    await db.prepare("INSERT INTO rule_conditions(id,rule_group_id,attribute_definition_id,condition_operator,expected_value_json,verification_status,evidence_id) VALUES ('c2','group','attr','EQ','\"MUNICIPALITY\"','VERIFIED','rule-evidence')").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_GRAPH", scenarioIds: [], conditionEvidenceIds: {} });
    await db.prepare("DELETE FROM rule_conditions WHERE id='c2'").run();
    await db.prepare("UPDATE rule_groups SET group_operator='AND' WHERE id='group'").run();
    await db.prepare("INSERT INTO rule_groups(id,rule_set_id,parent_group_id,group_operator) VALUES ('empty','rs','root','AND')").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_GRAPH" });
  });

  it("rejects nested groups beyond the eligibility evaluator depth bound", async () => {
    const db = await setup();
    let parent = "group";
    for (let depth = 0; depth < 16; depth++) {
      const id = `nested-${depth}`;
      await db.prepare("INSERT INTO rule_groups(id,rule_set_id,parent_group_id,group_operator) VALUES (?,'rs',?,'AND')")
        .bind(id, parent).run();
      parent = id;
    }
    await db.prepare("UPDATE rule_conditions SET rule_group_id=? WHERE id='c1'").bind(parent).run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_GRAPH",
      scenarioIds: [], conditionEvidenceIds: {} });
  });

  it("does not certify malformed, inactive, project or unsupported rule operands even with official evidence", async () => {
    const db = await setup();
    const changes = [
      ["rule_conditions", "expected_value_json", "not-json", '"MUNICIPALITY"'],
      ["rule_conditions", "expected_value_json", "42", '"MUNICIPALITY"'],
      ["rule_conditions", "expected_value_json", "null", '"MUNICIPALITY"'],
      ["rule_conditions", "condition_operator", "GEO_WITHIN", "EQ"],
      ["attribute_definitions", "active", 0, 1],
      ["attribute_definitions", "data_type", "DATE", "ENUM"],
    ] as const;
    for (const [table, column, invalid, original] of changes) {
      await db.prepare(`UPDATE ${table} SET ${column}=?`).bind(invalid).run();
      expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_OPERAND",
        scenarioIds: [], conditionEvidenceIds: {} });
      await db.prepare(`UPDATE ${table} SET ${column}=?`).bind(original).run();
      expect((await read(db)).status).toBe("VERIFIED");
    }
    await db.prepare("UPDATE attribute_definitions SET scope='PROJECT', attribute_key='project.type'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_OPERAND" });
    await db.prepare("UPDATE attribute_definitions SET scope='APPLICANT', attribute_key='applicant.type'").run();
    expect((await read(db)).status).toBe("VERIFIED");
    await db.prepare("UPDATE rule_conditions SET condition_operator='IN', expected_value_json='[]'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_RULE_OPERAND" });
    await db.prepare("UPDATE rule_conditions SET expected_value_json='[\"MUNICIPALITY\"]'").run();
    expect((await read(db)).status).toBe("VERIFIED");
  });
});
