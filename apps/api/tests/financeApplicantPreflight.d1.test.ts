// @ts-ignore -- Node test fixture: type availability differs between local install and CI.
import { readFileSync } from "node:fs";
// @ts-ignore -- Node test fixture: type availability differs between local install and CI.
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import { preflightFinanceApplicantValues } from "../src/financeApplicantPreflight";

const principal = "owner-a";
const asOf = "2026-01-04T00:00:00Z";
let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

async function setup() {
  mf = new Miniflare(convertV4MiniflareOptions({ name: "finance-applicant-preflight", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "finance-applicant-preflight" } }));
  const db = await mf.getD1Database("DB");
  // @ts-ignore -- Node test fixture: type availability differs between local install and CI.
  const migrations = resolve(import.meta.dirname, "../../../migrations");
  for (const file of ["0001_core_identity.sql", "0002_documents_provenance.sql",
    "0003_funding_projects_changes.sql", "0006_eligibility_rules.sql", "0007_applicant_profiles.sql",
    "0017_project_sharing.sql", "0018_project_owner_capabilities.sql",
    "0023_geography_applicant_rules.sql", "0029_applicant_profile_owner_identity.sql",
    "0030_applicant_sparse_ico_invalidation.sql"]) {
    const sql = readFileSync(resolve(migrations, file), "utf8")
      .replace(/^\s*--[^\n]*$/gm, "").replace(/^PRAGMA foreign_keys = ON;\s*/gm, "").replace(/\r?\n/g, " ");
    if (file.startsWith("0030_")) { await db.exec(sql); continue; }
    for (const statement of sql.split(";").map((part: string) => part.trim()).filter(Boolean))
      await db.prepare(statement).run();
  }
  await db.prepare("INSERT INTO applicant_profiles(id,user_id,applicant_type,created_at,updated_at) VALUES ('profile-a',?,'BUSINESS','2026-01-01T00:00:00Z',?)")
    .bind(principal, asOf).run();
  await db.prepare("INSERT INTO applicant_profiles(id,user_id,applicant_type,created_at,updated_at) VALUES ('profile-b','owner-b','BUSINESS',?,?)")
    .bind(asOf, asOf).run();
  await db.prepare("INSERT INTO source_registry(id,code,name,base_url,adapter_key,authority,retrieval_mode,refresh_minutes) VALUES ('src','ARES_PROFILE','Source','https://example.test','fixture','OFFICIAL','HTTP',60)").run();
  await db.prepare("INSERT INTO source_documents(id,source_id,document_type,source_url,first_seen_at) VALUES ('doc','src','OTHER','https://example.test/doc','2026-01-01T00:00:00Z')").run();
  await db.prepare("INSERT INTO document_versions(id,source_document_id,sha256,retrieved_at,mime_type,object_key,extraction_status) VALUES ('dv','doc','hash','2026-01-01T00:00:00Z','text/plain','raw','EXTRACTED')").run();
  await db.prepare("INSERT INTO field_evidence(id,entity_type,entity_id,field_path,document_version_id,verification_status,created_at) VALUES ('ev','APPLICANT_ATTRIBUTE_VALUE','value-a','applicant.ico','dv','VERIFIED','2026-01-02T00:00:00Z')").run();
  await db.prepare(`INSERT INTO applicant_attribute_values(id,applicant_profile_id,attribute_definition_id,value_type,value_json,
    source_kind,observed_at,verified_at,verification_status,evidence_id)
    VALUES ('value-a','profile-a','attr-applicant-ico','STRING','"12345678"','ARES',
      '2026-01-02T00:00:00Z','2026-01-03T00:00:00Z','VERIFIED','ev')`).run();
  return db;
}

const read = (db: any, owner = principal, profile = "profile-a", cutoff = asOf) =>
  preflightFinanceApplicantValues(db, owner, profile, cutoff);

describe("finance applicant preflight on canonical D1", () => {
  it("fails closed on rejected, incomplete or malformed snapshot reads without releasing IDs", async () => {
    const db = await setup();
    const normal = await read(db);
    expect(normal.status).toBe("STRUCTURE_ONLY");
    for (const brokenBatch of [
      async () => { throw new Error("D1 unavailable"); },
      async (statements: any[]) => (await db.batch(statements)).slice(0, 1),
      async () => null,
      async (statements: any[]) => {
        const rows = await db.batch(statements);
        return rows.map((row: any, index: number) => index === 0 ? { ...row, results: undefined } : row);
      },
      async (statements: any[]) => {
        const rows = await db.batch(statements);
        return rows.map((row: any, index: number) => index === 1 ? { ...row, results: undefined } : row);
      },
      async (statements: any[]) => {
        const rows = await db.batch(statements);
        return rows.map((row: any, index: number) => index === 1 ? { ...row, success: false } : row);
      },
    ]) {
      const brokenDb = { prepare: db.prepare.bind(db), batch: brokenBatch };
      await expect(read(brokenDb)).resolves.toEqual({ status: "ERROR", reason: "SNAPSHOT_READ_FAILED",
        profileId: null, attributeValueIds: [], evidenceIds: [] });
    }
    expect(await read(db)).toEqual(normal);
  });

  it("returns only structural identifiers for an owned official scalar value", async () => {
    const db = await setup();
    const result = await read(db);
    expect(result).toEqual({ status: "STRUCTURE_ONLY", reason: "OWNED_OFFICIAL_ATTRIBUTE_REFERENCES_ONLY",
      profileId: "profile-a", attributeValueIds: ["value-a"], evidenceIds: ["ev"] });
    expect(JSON.stringify(result)).not.toContain("12345678");
    expect(await read(db, principal, "profile-b")).toMatchObject({ status: "NEEDS_INFORMATION",
      reason: "PROFILE_NOT_OWNED", profileId: null, attributeValueIds: [], evidenceIds: [] });
    expect(await read(db, "owner-b")).toMatchObject({ status: "NEEDS_INFORMATION", reason: "PROFILE_NOT_OWNED" });
  });

  it("fails closed on wrong evidence entity, path, verification, document and source", async () => {
    const db = await setup();
    for (const [table, column, bad, good] of [
      ["field_evidence", "entity_type", "GRANT_CALL_VERSION", "APPLICANT_ATTRIBUTE_VALUE"],
      ["field_evidence", "entity_id", "other-value", "value-a"],
      ["field_evidence", "field_path", "applicant.type", "applicant.ico"],
      ["field_evidence", "verification_status", "NEEDS_REVIEW", "VERIFIED"],
      ["document_versions", "extraction_status", "QUARANTINED", "EXTRACTED"],
      ["source_registry", "authority", "SECONDARY", "OFFICIAL"],
      ["source_registry", "code", "CZSO_POPULATION", "ARES_PROFILE"],
      ["applicant_attribute_values", "verification_status", "PARTIALLY_VERIFIED", "VERIFIED"],
      ["applicant_attribute_values", "source_kind", "USER", "ARES"],
      ["applicant_attribute_values", "evidence_id", null, "ev"],
    ] as const) {
      await db.prepare(`UPDATE ${table} SET ${column} = ?`).bind(bad).run();
      expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", attributeValueIds: [], evidenceIds: [] });
      await db.prepare(`UPDATE ${table} SET ${column} = ?`).bind(good).run();
      expect((await read(db)).status).toBe("STRUCTURE_ONLY");
    }
  });

  it("rejects mismatched, unsupported and malformed value types", async () => {
    const db = await setup();
    for (const [table, column, bad, good] of [
      ["applicant_attribute_values", "value_type", "ENUM", "STRING"],
      ["applicant_attribute_values", "value_json", "42", '"12345678"'],
      ["attribute_definitions", "data_type", "DATE", "STRING"],
      ["attribute_definitions", "active", 0, 1],
    ] as const) {
      await db.prepare(`UPDATE ${table} SET ${column} = ? WHERE id = ?`)
        .bind(bad, table === "attribute_definitions" ? "attr-applicant-ico" : "value-a").run();
      expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_ATTRIBUTE_VALUE" });
      await db.prepare(`UPDATE ${table} SET ${column} = ? WHERE id = ?`)
        .bind(good, table === "attribute_definitions" ? "attr-applicant-ico" : "value-a").run();
    }
  });

  it("rejects embedded NUL and byte-oversize JSON before parsing a truncated scalar", async () => {
    const db = await setup();
    await db.prepare("UPDATE applicant_attribute_values SET value_json='\"12345678\"' || char(0) || 'suffix' WHERE id='value-a'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_ATTRIBUTE_VALUE",
      attributeValueIds: [], evidenceIds: [] });
    await db.prepare("UPDATE applicant_attribute_values SET value_json=? WHERE id='value-a'")
      .bind(JSON.stringify("x".repeat(4096))).run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNSUPPORTED_ATTRIBUTE_VALUE" });
  });

  it("rejects missing, reversed or future timestamps and an invalid cutoff", async () => {
    const db = await setup();
    for (const [table, column, bad, good] of [
      ["applicant_attribute_values", "verified_at", null, "2026-01-03T00:00:00Z"],
      ["applicant_attribute_values", "observed_at", "2026-01-04T00:00:00Z", "2026-01-02T00:00:00Z"],
      ["applicant_attribute_values", "observed_at", "2026-01-03T00:00:00Z", "2026-01-02T00:00:00Z"],
      ["applicant_attribute_values", "observed_at", "bad", "2026-01-02T00:00:00Z"],
      ["field_evidence", "created_at", "2026-01-04T00:00:00Z", "2026-01-02T00:00:00Z"],
      ["document_versions", "retrieved_at", "2026-01-04T00:00:00Z", "2026-01-01T00:00:00Z"],
      ["source_documents", "first_seen_at", "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"],
      ["applicant_profiles", "created_at", "2026-01-04T00:00:00Z", "2026-01-01T00:00:00Z"],
    ] as const) {
      await db.prepare(`UPDATE ${table} SET ${column} = ?`).bind(bad).run();
      expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "INCONSISTENT_ATTRIBUTE_TIMESTAMPS" });
      await db.prepare(`UPDATE ${table} SET ${column} = ?`).bind(good).run();
    }
    await db.prepare("UPDATE document_versions SET retrieved_at='2026-01-02T00:00:00Z'").run();
    await db.prepare("UPDATE applicant_attribute_values SET observed_at='2026-01-01T00:00:00Z'").run();
    expect((await read(db)).status).toBe("STRUCTURE_ONLY");
    await db.prepare("UPDATE applicant_attribute_values SET observed_at='2026-01-02T00:00:00Z'").run();
    await db.prepare("UPDATE document_versions SET retrieved_at='2026-01-01T00:00:00Z'").run();
    expect(await read(db, principal, "profile-a", "2026-01-02T00:00:00Z"))
      .toMatchObject({ status: "NEEDS_INFORMATION", reason: "INCONSISTENT_ATTRIBUTE_TIMESTAMPS" });
    expect(await read(db, principal, "profile-a", "bad"))
      .toMatchObject({ status: "ERROR", reason: "INVALID_PREFLIGHT_INPUT" });
  });

  it("observes canonical sparse invalidation and the row bound", async () => {
    const db = await setup();
    await db.prepare("UPDATE applicant_profiles SET ico='12345678' WHERE id='profile-a'").run();
    expect(await read(db)).toMatchObject({ status: "NEEDS_INFORMATION", reason: "UNVERIFIED_OFFICIAL_ATTRIBUTE_EVIDENCE" });
    await db.prepare("UPDATE applicant_attribute_values SET verification_status='VERIFIED', verified_at='2026-01-03T00:00:00Z'").run();
    for (let i = 0; i < 128; i++) {
      await db.prepare("INSERT INTO attribute_definitions(id,attribute_key,scope,label_cs,data_type) VALUES (?,?, 'APPLICANT','Extra','STRING')")
        .bind(`extra-${i}`, `applicant.extra_${i}`).run();
      await db.prepare(`INSERT INTO applicant_attribute_values(id,applicant_profile_id,attribute_definition_id,value_type,value_json,
        source_kind,observed_at,verified_at,verification_status)
        VALUES (?,'profile-a',?,'STRING','"x"','USER','2026-01-02T00:00:00Z',NULL,'USER_DECLARED')`)
        .bind(`value-${i}`, `extra-${i}`).run();
    }
    expect(await read(db)).toEqual({ status: "ERROR", reason: "ATTRIBUTE_LIMIT_EXCEEDED",
      profileId: null, attributeValueIds: [], evidenceIds: [] });
  }, 30000);
});
