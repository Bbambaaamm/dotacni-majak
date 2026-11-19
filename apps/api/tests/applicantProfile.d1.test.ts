import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import type { Env } from "../src/env";
import { handleRequest } from "../src/index";
import { hashOwnerToken } from "../src/projectAccess";

const token = "A".repeat(43);
const rotated = "B".repeat(43);
const other = "C".repeat(43);
const invalid = "X".repeat(43);
const now = "2026-01-01T00:00:00Z";
const projectA = "prj_" + "a".repeat(32);
const projectB = "prj_" + "b".repeat(32);

let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

async function setup(): Promise<Env> {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "profile-review-test",
    modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "profile-review-test" },
  }));
  const db = await mf.getD1Database("DB");
  const migrations = resolve(import.meta.dirname, "../../../migrations");
  // Apply the relevant real migrations against workerd D1, one SQL
  // statement at a time (including the ownership migration under test).
  for (const file of [
    "0001_core_identity.sql", "0002_documents_provenance.sql",
    "0003_funding_projects_changes.sql",
    "0006_eligibility_rules.sql", "0007_applicant_profiles.sql",
    "0017_project_sharing.sql", "0018_project_owner_capabilities.sql",
    "0023_geography_applicant_rules.sql",
    "0029_applicant_profile_owner_identity.sql",
  ]) {
    const sql = readFileSync(resolve(migrations, file), "utf8")
      .replace(/^\s*--[^\n]*$/gm, "")
      .replace(/^PRAGMA foreign_keys = ON;\s*/gm, "")
      .replace(/\r?\n/g, " ");
    for (const statement of sql.split(";").map((part) => part.trim()).filter(Boolean)) {
      await db.prepare(statement).run();
    }
  }
  await db.prepare("INSERT INTO applicant_types(id,code,name_cs) VALUES (?,?,?)")
    .bind("type-1", "BUSINESS", "Business").run();
  await db.prepare("INSERT INTO geographies(id,geography_type,name,country_code) VALUES (?,?,?,?)")
    .bind("geo-1", "MUNICIPALITY", "Test", "CZ").run();
  for (const [id, principal, capability] of [
    [projectA, "anonymous:" + projectA, token],
    [projectB, "anonymous:" + projectB, other],
  ]) {
    await db.prepare(
      `INSERT INTO projects(id,owner_user_id,natural_language_intent,currency_code,created_at,updated_at)
       VALUES (?,?,?,?,?,?)`,
    ).bind(id, principal, "test", "CZK", now, now).run();
    await db.prepare(
      `INSERT INTO project_owner_capabilities(project_id,token_hash,created_at) VALUES (?,?,?)`,
    ).bind(id, await hashOwnerToken(capability), now).run();
  }
  return {
    DB: db as unknown as Env["DB"],
    RAW: { async head() { return null; } },
    SEARCH: { async describe() { return {}; } },
    ENVIRONMENT: "local",
  };
}

function request(method: string, capability: string, body?: unknown): Request {
  return new Request("https://example.test/applicant-profile", {
    method,
    headers: { authorization: `Bearer ${capability}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function seedTrustedSources(env: Env, sources: Record<string, unknown>): Promise<void> {
  await env.DB.prepare("UPDATE applicant_profiles SET field_sources_json = ? WHERE user_id = ?")
    .bind(JSON.stringify(sources), "anonymous:" + projectA).run();
}

const input = { applicantType: "BUSINESS", ico: "12345678", fieldSources: {} };

describe("applicant profile with real D1", () => {
  it("rejects unknown and revoked tokens and keeps the profile through rotation", async () => {
    const env = await setup();
    for (const method of ["GET", "PUT", "DELETE"]) {
      const response = await handleRequest(request(method, invalid, method === "PUT" ? input : undefined), env);
      expect(response.status).toBe(404);
      expect((await response.json() as { error: string }).error).toBe("OWNER_CAPABILITY_INVALID");
    }
    const saved = await handleRequest(request("PUT", token, input), env);
    expect(saved.status).toBe(200);
    const id = ((await saved.json()) as { profile: { id: string } }).profile.id;
    const trusted = { sourceKind: "ARES", observedAt: "2026-09-25T12:00:00Z", verificationStatus: "VERIFIED" };
    await seedTrustedSources(env, { ico: trusted });
    await env.DB.prepare("UPDATE project_owner_capabilities SET token_hash = ?, generation = 2, rotated_at = ? WHERE project_id = ?")
      .bind(await hashOwnerToken(rotated), now, projectA).run();
    expect((await handleRequest(request("GET", token), env)).status).toBe(404);
    const afterRotation = await handleRequest(request("GET", rotated), env);
    expect(afterRotation.status).toBe(200);
    expect(((await afterRotation.json()) as { profile: { id: string; fieldSources: Record<string, unknown>; lastResolvedAt: string } }).profile)
      .toMatchObject({ id, fieldSources: { ico: trusted }, lastResolvedAt: trusted.observedAt });
    await env.DB.prepare("UPDATE project_owner_capabilities SET revoked_at = ? WHERE project_id = ?")
      .bind(now, projectA).run();
    for (const method of ["GET", "PUT", "DELETE"]) {
      const response = await handleRequest(request(method, rotated, method === "PUT" ? input : undefined), env);
      expect(response.status).toBe(404);
      expect((await response.json() as { error: string }).error).toBe("OWNER_CAPABILITY_INVALID");
    }
  });

  it("rejects initial and repeated forged official claims without modifying a trusted row", async () => {
    const env = await setup();
    const source = { sourceKind: "ARES", observedAt: "2026-09-25T12:00:00Z", verificationStatus: "VERIFIED" };
    const forged = { applicantType: "BUSINESS", ico: "12345678", fieldSources: { ico: source } };
    for (const method of ["PUT", "POST"] as const) {
      const response = await handleRequest(request(method, token, forged), env);
      expect(response.status).toBe(400);
      expect((await response.json() as { error: string }).error).toBe("UNTRUSTED_FIELD_SOURCE");
    }
    expect((await env.DB.prepare("SELECT id FROM applicant_profiles").all()).results).toHaveLength(0);

    expect((await handleRequest(request("PUT", token, input), env)).status).toBe(200);
    await seedTrustedSources(env, { ico: source });
    const before = await env.DB.prepare("SELECT id, ico, field_sources_json, updated_at FROM applicant_profiles").first();
    for (const method of ["PUT", "POST", "PUT"] as const) {
      const response = await handleRequest(request(method, token, forged), env);
      expect(response.status).toBe(400);
      expect((await response.json() as { error: string }).error).toBe("UNTRUSTED_FIELD_SOURCE");
      expect(await env.DB.prepare("SELECT id, ico, field_sources_json, updated_at FROM applicant_profiles").first()).toEqual(before);
    }
    const profile = (await (await handleRequest(request("GET", token), env)).json() as { profile: { fieldSources: Record<string, unknown>; lastResolvedAt: string } }).profile;
    expect(profile.fieldSources).toEqual({ ico: source });
    expect(profile.lastResolvedAt).toBe(source.observedAt);
    const refresh = await handleRequest(new Request("https://example.test/applicant-profile/last-resolved", {
      headers: { authorization: `Bearer ${token}` },
    }), env);
    expect(await refresh.json()).toEqual({ lastResolvedAt: source.observedAt });
  });

  it("atomically upserts one row under concurrent requests and allows shared IČO", async () => {
    const env = await setup();
    const writes = await Promise.all([
      { ...input, organisationName: "Owner A" },
      { applicantType: "BUSINESS", municipalityCode: "123456" },
      { applicantType: "BUSINESS", vatStatus: "PAYER" },
      { applicantType: "BUSINESS", czNaceCodes: ["93.12"] },
    ].map((body) => handleRequest(request("PUT", token, body), env)));
    expect(writes.every((response) => response.status === 200)).toBe(true);
    const ownerProfile = await handleRequest(request("GET", token), env);
    expect((await ownerProfile.json() as { profile: Record<string, unknown> }).profile).toMatchObject({
      ico: input.ico, organisationName: "Owner A", municipalityCode: "123456",
      vatStatus: "PAYER", czNaceCodes: ["93.12"],
    });
    const otherWrite = await handleRequest(request("PUT", other, { ...input, organisationName: "Owner B" }), env);
    expect(otherWrite.status).toBe(200);
    const rows = await env.DB.prepare("SELECT user_id, ico FROM applicant_profiles WHERE ico = ?")
      .bind(input.ico).all<{ user_id: string; ico: string }>();
    expect(rows.results).toHaveLength(2);
    expect(new Set((rows.results as { user_id: string }[]).map((row) => row.user_id)).size).toBe(2);
  });

  it("round-trips provenance and local identifiers through sparse and clearing writes", async () => {
    const env = await setup();
    const source = { sourceKind: "ARES", observedAt: "2026-09-25T12:00:00Z", verificationStatus: "VERIFIED" };
    const initial = { ...input, schemaVersion: "1.0.0", applicantTypeId: "type-1",
      seatGeographyId: "geo-1", czNaceCodes: ["93.12"] };
    expect((await handleRequest(request("POST", token, initial), env)).status).toBe(200);
    await seedTrustedSources(env, { ico: source });
    const changed = await handleRequest(request("PUT", token, { applicantType: "BUSINESS", organisationName: "Updated" }), env);
    expect(changed.status).toBe(200);
    const get = await handleRequest(request("GET", token), env);
    expect(get.status).toBe(200);
    expect((await get.json() as { profile: Record<string, unknown> }).profile).toMatchObject({
      schemaVersion: "1.0.0", applicantTypeId: "type-1", seatGeographyId: "geo-1",
      ico: input.ico, organisationName: "Updated", czNaceCodes: ["93.12"],
      fieldSources: { ico: source }, lastResolvedAt: source.observedAt,
    });
    const cleared = await handleRequest(request("POST", token, {
      applicantType: "BUSINESS", applicantTypeId: null, seatGeographyId: null,
      ico: null, czNaceCodes: [], fieldSources: {},
    }), env);
    expect(cleared.status).toBe(200);
    expect((await cleared.json() as { profile: Record<string, unknown> }).profile).toMatchObject({
      applicantTypeId: null, seatGeographyId: null, ico: null,
      organisationName: "Updated", czNaceCodes: [], fieldSources: {}, lastResolvedAt: null,
    });
  });

  it("removes only changed IČO provenance on a sparse PUT in workerd D1", async () => {
    const env = await setup();
    const icoSource = { sourceKind: "ARES", observedAt: "2026-09-25T12:00:00Z", verificationStatus: "VERIFIED" };
    const municipalitySource = { sourceKind: "CZSO", observedAt: "2026-09-23T00:00:00Z", verificationStatus: "VERIFIED" };
    const initial = await handleRequest(request("PUT", token, {
      applicantType: "BUSINESS", ico: "12345678", municipalityCode: "123456",
    }), env);
    expect(initial.status).toBe(200);
    await seedTrustedSources(env, { ico: icoSource, municipalityCode: municipalitySource });

    const changed = await handleRequest(request("PUT", token, { applicantType: "BUSINESS", ico: "87654321", municipalityCode: "123456" }), env);
    expect(changed.status).toBe(200);
    expect((await changed.json() as { profile: Record<string, unknown> }).profile).toMatchObject({
      ico: "87654321", municipalityCode: "123456",
      fieldSources: { municipalityCode: municipalitySource }, lastResolvedAt: municipalitySource.observedAt,
    });
    const get = await handleRequest(request("GET", token), env);
    expect((await get.json() as { profile: { fieldSources: Record<string, unknown> } }).profile.fieldSources.ico).toBeUndefined();

    // A client cannot restore the old official claim on an identical retry.
    for (const method of ["PUT", "POST"] as const) {
      const forged = await handleRequest(request(method, token, {
        applicantType: "BUSINESS", ico: "87654321",
        fieldSources: { ico: icoSource },
      }), env);
      expect(forged.status).toBe(400);
      expect((await forged.json() as { error: string }).error).toBe("UNTRUSTED_FIELD_SOURCE");
    }

    const cleared = await handleRequest(request("PUT", token, { applicantType: "BUSINESS", ico: null }), env);
    expect(cleared.status).toBe(200);
    expect((await cleared.json() as { profile: { ico: string | null; fieldSources: Record<string, unknown>; lastResolvedAt: string } }).profile)
      .toMatchObject({ ico: null, fieldSources: { municipalityCode: municipalitySource }, lastResolvedAt: municipalitySource.observedAt });
  });

  it("clears normalized type ID and stale type provenance when applicantType changes", async () => {
    const env = await setup();
    const typeSource = { sourceKind: "ARES", observedAt: "2026-10-01T09:00:00Z", verificationStatus: "VERIFIED" };
    const municipalitySource = { sourceKind: "CZSO", observedAt: "2026-09-23T00:00:00Z", verificationStatus: "VERIFIED" };
    expect((await handleRequest(request("PUT", token, {
      applicantType: "BUSINESS", applicantTypeId: "type-1", municipalityCode: "123456",
    }), env)).status).toBe(200);
    await seedTrustedSources(env, { applicantType: typeSource, applicantTypeId: typeSource, municipalityCode: municipalitySource });
    const sameType = await handleRequest(request("PUT", token, { applicantType: "BUSINESS" }), env);
    expect((await sameType.json() as { profile: { applicantTypeId: string } }).profile.applicantTypeId).toBe("type-1");

    const changed = await handleRequest(request("PUT", token, { applicantType: "MUNICIPALITY" }), env);
    expect(changed.status).toBe(200);
    const profile = (await changed.json() as { profile: Record<string, unknown> }).profile;
    expect(profile).toMatchObject({
      applicantType: "MUNICIPALITY", applicantTypeId: null,
      fieldSources: { municipalityCode: municipalitySource }, lastResolvedAt: municipalitySource.observedAt,
    });
    expect(profile.fieldSources).toEqual({ municipalityCode: municipalitySource });
  });
});
