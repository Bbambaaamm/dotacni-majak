// @ts-nocheck -- Miniflare D1 fixture follows the existing API integration-test convention.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

import type { D1DatabaseLike, Env } from "../src/env";
import { getGrantDetail } from "../src/grantDetail";
import { handleRequest } from "../src/index";

let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

async function fixture() {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "grant-detail-identity-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "grant-detail-identity-test" },
  }));
  const db = await mf.getD1Database("DB");
  const migrations = resolve(import.meta.dirname, "../../../migrations");
  for (const file of ["0001_core_identity.sql", "0002_documents_provenance.sql",
    "0003_funding_projects_changes.sql", "0014_funding_instrument_type.sql"]) {
    const sql = readFileSync(resolve(migrations, file), "utf8")
      .replace(/^\s*--[^\n]*$/gm, "").replace(/^PRAGMA foreign_keys = ON;\s*/gm, "").replace(/\r?\n/g, " ");
    for (const part of sql.split(";").map((value) => value.trim()).filter(Boolean)) {
      await db.prepare(part).run();
    }
  }
  for (const statement of [
    "INSERT INTO providers(id,name,provider_type) VALUES ('provider','Provider','NATIONAL')",
    "INSERT INTO programmes(id,provider_id,name,funding_origin) VALUES ('programme','provider','Programme','CZ_NATIONAL')",
    "INSERT INTO grant_calls(id,programme_id,canonical_slug,current_status,current_title,first_seen_at,created_at,updated_at) VALUES ('call-a','programme','call-a','OPEN','A','2026','2026','2026')",
    "INSERT INTO grant_calls(id,programme_id,canonical_slug,current_status,current_title,first_seen_at,created_at,updated_at) VALUES ('call-b','programme','call-b','OPEN','B','2026','2026','2026')",
    "INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at) VALUES ('version-a','call-a',1,'2026','A','OPEN','VERIFIED','2026')",
    "INSERT INTO grant_call_versions(id,grant_call_id,version_number,captured_at,title,status,verification_status,created_at) VALUES ('version-b','call-b',1,'2026','B','OPEN','VERIFIED','2026')",
    "UPDATE grant_calls SET current_version_id='version-a' WHERE id='call-a'",
    "UPDATE grant_calls SET current_version_id='version-b' WHERE id='call-b'",
  ]) await db.prepare(statement).run();
  const database = db as unknown as D1DatabaseLike;
  const env: Env = { DB: database, ENVIRONMENT: "local",
    RAW: { head: async () => null }, SEARCH: { describe: async () => ({}) } };
  return { db, database, env };
}

describe("grant detail current-version identity on real D1", () => {
  it("retains submission dates from the version when only a non-application deadline is normalized", async () => {
    const { db, database, env } = await fixture();
    await db.prepare("UPDATE grant_call_versions SET submission_open_at='2027-01-01T08:00:00Z', submission_close_at='2027-02-01T17:00:00Z' WHERE id='version-a'").run();
    await db.prepare("INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,ends_at) VALUES ('project-finish','version-a','PROJECT_FINISH','2028-01-01T00:00:00Z')").run();
    const detail = await getGrantDetail(database, "call-a");
    expect(detail?.deadlines).toEqual([
      expect.objectContaining({ id: "project-finish", type: "PROJECT_FINISH" }),
      expect.objectContaining({ type: "APPLICATION_WINDOW", startsAt: "2027-01-01T08:00:00Z", endsAt: "2027-02-01T17:00:00Z", evidenceId: null }),
    ]);
    const response = await handleRequest(new Request("https://example.test/grants/call-a"), env);
    expect(response.status).toBe(200);
    expect((await response.json()).deadlines).toEqual(detail?.deadlines);

    await db.prepare("INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,ends_at) VALUES ('application-close','version-a','APPLICATION_CLOSE','2027-02-01T17:00:00Z')").run();
    const normalized = await getGrantDetail(database, "call-a");
    expect(normalized?.deadlines).toEqual([
      expect.objectContaining({ id: "application-close", type: "APPLICATION_CLOSE", endsAt: "2027-02-01T17:00:00Z" }),
      expect.objectContaining({ id: "project-finish", type: "PROJECT_FINISH" }),
      expect.objectContaining({ id: "version-a:submission-open", type: "APPLICATION_OPEN", startsAt: "2027-01-01T08:00:00Z", endsAt: null, timezone: null, evidenceId: null }),
    ]);
    const partialResponse = await handleRequest(new Request("https://example.test/grants/call-a"), env);
    expect(partialResponse.status).toBe(200);
    expect((await partialResponse.json()).deadlines).toEqual(normalized?.deadlines);

    await db.prepare("DELETE FROM grant_deadlines WHERE id='application-close'").run();
    await db.prepare("INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,starts_at) VALUES ('application-open','version-a','APPLICATION_OPEN','2027-01-01T08:00:00Z')").run();
    expect((await getGrantDetail(database, "call-a"))?.deadlines).toEqual([
      expect.objectContaining({ id: "application-open", type: "APPLICATION_OPEN" }),
      expect.objectContaining({ id: "project-finish", type: "PROJECT_FINISH" }),
      expect.objectContaining({ id: "version-a:submission-close", type: "APPLICATION_CLOSE", startsAt: null, endsAt: "2027-02-01T17:00:00Z", evidenceId: null }),
    ]);
    await db.prepare("INSERT INTO grant_deadlines(id,grant_call_version_id,deadline_type,ends_at) VALUES ('application-close','version-a','APPLICATION_CLOSE','2027-02-01T17:00:00Z')").run();
    expect((await getGrantDetail(database, "call-a"))?.deadlines.map((deadline) => deadline.id)).toEqual(["application-open", "application-close", "project-finish"]);
  });

  it("serves its own current version, but never attributes another call's version to it", async () => {
    const { db, database, env } = await fixture();
    expect((await getGrantDetail(database, "call-a"))?.title).toBe("A");
    await db.prepare("UPDATE grant_calls SET current_version_id='version-b' WHERE id='call-a'").run();
    expect(await getGrantDetail(database, "call-a")).toBeNull();
    const response = await handleRequest(new Request("https://example.test/grants/call-a"), env);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "GRANT_NOT_FOUND" });
    expect((await getGrantDetail(database, "call-b"))?.title).toBe("B");
  });
});
