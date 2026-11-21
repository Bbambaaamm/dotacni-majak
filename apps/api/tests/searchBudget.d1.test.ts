import { afterEach, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import type { D1DatabaseLike, Env } from "../src/env";
import { handleRequest } from "../src/index";
import { searchGrants } from "../src/search";

let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

it("real D1 filters only verified CZK grant project-cost intervals before pages and facets", async () => {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "search-budget-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "search-budget-test" },
  }));
  const db = await mf.getD1Database("DB");
  for (const sql of [
    "CREATE TABLE grant_search_documents (grant_call_version_id TEXT PRIMARY KEY, title TEXT, summary TEXT, status TEXT, submission_close_at TEXT)",
    "CREATE TABLE grant_call_versions (id TEXT PRIMARY KEY, grant_call_id TEXT, official_detail_url TEXT, funding_instrument_type TEXT, captured_at TEXT NOT NULL DEFAULT '2026-09-26T20:00:00Z', verification_status TEXT NOT NULL DEFAULT 'VERIFIED')",
    "CREATE TABLE grant_calls (id TEXT PRIMARY KEY, programme_id TEXT)",
    "CREATE TABLE programmes (id TEXT PRIMARY KEY, provider_id TEXT)",
    "CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT)",
    "CREATE VIRTUAL TABLE grant_search_fts USING fts5(grant_call_version_id UNINDEXED, title, summary, supported_activities, eligible_costs, keywords)",
    "CREATE TABLE funding_scenarios (id TEXT PRIMARY KEY, grant_call_version_id TEXT, instrument_type TEXT, currency_code TEXT, project_cost_min_minor INTEGER, project_cost_max_minor INTEGER, evidence_id TEXT)",
    "CREATE TABLE field_evidence (id TEXT PRIMARY KEY, entity_type TEXT, entity_id TEXT, field_path TEXT, document_version_id TEXT, verification_status TEXT)",
    "CREATE TABLE document_versions (id TEXT PRIMARY KEY, source_document_id TEXT)",
    "CREATE TABLE source_documents (id TEXT PRIMARY KEY, grant_call_id TEXT)",
    "INSERT INTO providers VALUES ('p', 'Test provider')",
    "INSERT INTO programmes VALUES ('pr', 'p')",
    "INSERT INTO grant_calls VALUES ('g', 'pr')",
    "INSERT INTO source_documents VALUES ('doc', 'g')",
    "INSERT INTO document_versions VALUES ('dv', 'doc')",
  ]) await db.prepare(sql).run();
  const cases: Array<[string, string, string, number | null, number | null, string, string, string]> = [
    ["a", "GRANT", "CZK", 10000, 20000, "VERIFIED", "GRANT", "OPEN"],
    ["b", "GRANT", "CZK", 10000, 20000, "VERIFIED", "GRANT", "PLANNED"],
    ["too-small", "GRANT", "CZK", 30000, 40000, "VERIFIED", "GRANT", "OPEN"],
    ["too-large", "GRANT", "CZK", 100, 5000, "VERIFIED", "GRANT", "OPEN"],
    ["unknown", "GRANT", "CZK", null, null, "VERIFIED", "GRANT", "OPEN"],
    ["one-bound", "GRANT", "CZK", null, 20000, "VERIFIED", "GRANT", "OPEN"],
    ["unverified", "GRANT", "CZK", 10000, 20000, "AUTO_EXTRACTED", "GRANT", "OPEN"],
    ["foreign", "GRANT", "EUR", 10000, 20000, "VERIFIED", "GRANT", "OPEN"],
    ["loan", "LOAN", "CZK", 10000, 20000, "VERIFIED", "LOAN", "OPEN"],
    ["mismatch", "GRANT", "CZK", 10000, 20000, "VERIFIED", "LOAN", "OPEN"],
    ["wrong-path", "GRANT", "CZK", 10000, 20000, "VERIFIED", "GRANT", "OPEN"],
    ["wrong-document", "GRANT", "CZK", 10000, 20000, "VERIFIED", "GRANT", "OPEN"],
    ["no-evidence", "GRANT", "CZK", 10000, 20000, "VERIFIED", "GRANT", "OPEN"],
  ];
  for (const [id, type, currency, min, max, verification, versionType, status] of cases) {
    await db.prepare("INSERT INTO grant_call_versions (id,grant_call_id,official_detail_url,funding_instrument_type) VALUES (?, 'g', NULL, ?)").bind(id, versionType).run();
    await db.prepare("INSERT INTO grant_search_documents VALUES (?, 'alpha grant', '', ?, ?)")
      .bind(id, status, `2027-01-${id === "a" ? "01" : "02"}T00:00:00Z`).run();
    await db.prepare("INSERT INTO grant_search_fts(grant_call_version_id, title) VALUES (?, 'alpha grant')").bind(id).run();
    await db.prepare("INSERT INTO field_evidence VALUES (?, 'GRANT_CALL_VERSION', ?, ?, 'dv', ?)")
      .bind(`fe-${id}`, id, `/funding_scenarios/fs-${id}`, verification).run();
    await db.prepare("INSERT INTO funding_scenarios VALUES (?, ?, ?, ?, ?, ?, ?)")
      .bind(`fs-${id}`, id, type, currency, min, max, `fe-${id}`).run();
  }
  await db.prepare("UPDATE field_evidence SET field_path='/title' WHERE id='fe-wrong-path'").run();
  await db.prepare("INSERT INTO grant_calls VALUES ('other-g', 'pr')").run();
  await db.prepare("INSERT INTO source_documents VALUES ('other-doc', 'other-g')").run();
  await db.prepare("INSERT INTO document_versions VALUES ('other-dv', 'other-doc')").run();
  await db.prepare("UPDATE field_evidence SET document_version_id='other-dv' WHERE id='fe-wrong-document'").run();
  await db.prepare("UPDATE funding_scenarios SET evidence_id=NULL WHERE id='fs-no-evidence'").run();
  const typed = db as unknown as D1DatabaseLike;
  const env: Env = { DB: typed, ENVIRONMENT: "local", RAW: { head: async () => null }, SEARCH: { describe: async () => ({}) } };
  const response = await handleRequest(new Request("https://example.test/search?intent=alpha&projectBudgetCzk=150"), env);
  expect(response.status).toBe(200);
  const results = (await response.json() as { results: Array<{ grantCallVersionId: string; capturedAt: string; verificationStatus: string }> }).results;
  expect(results.map((row) => row.grantCallVersionId).sort()).toEqual(["a", "b"]);
  expect(results).toEqual(expect.arrayContaining([expect.objectContaining({ grantCallVersionId: "a",
    capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED" })]));
  const invalid = await handleRequest(new Request("https://example.test/search?intent=alpha&projectBudgetCzk=150&projectBudgetCzk=151"), env);
  expect(invalid.status).toBe(400);
  expect(await invalid.json()).toEqual({ error: "INVALID_PROJECT_BUDGET" });
  for (const budget of ["100", "200"]) {
    const boundary = await searchGrants(typed, "alpha", 20, null, null, null, null, null, null, null, null, budget);
    expect(new Set(boundary.results.map((row) => row.grantCallVersionId))).toEqual(new Set(["a", "b"]));
  }
  for (const budget of ["99", "201"]) {
    const outside = await searchGrants(typed, "alpha", 20, null, null, null, null, null, null, null, null, budget);
    expect(outside.results).toEqual([]);
  }
  for (const sort of [null, "DEADLINE", "DEADLINE_LATEST"]) {
    const first = await searchGrants(typed, "alpha", 1, null, null, null, null, null, sort, null, null, "150");
    expect(first.results).toHaveLength(1);
    expect(first.facets?.status).toEqual({ OPEN: 1, PLANNED: 1, ANNOUNCED: 0 });
    expect(first.facets?.providers).toEqual([{ name: "Test provider", count: 2 }]);
    expect(first.nextCursor).toBeTruthy();
    const second = await searchGrants(typed, "alpha", 1, first.nextCursor, null, null, null, null, sort, null, null, "150");
    expect(new Set([...first.results, ...second.results].map((row) => row.grantCallVersionId)))
      .toEqual(new Set(["a", "b"]));
    expect(second.nextCursor).toBeNull();
    await expect(searchGrants(typed, "alpha", 1, first.nextCursor, null, null, null, null, sort))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(typed, "alpha", 1, first.nextCursor, null, null, null, null, sort, null, null, "151"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
  }
  for (const bad of ["", "-1", "1.5", "01", "1e2", "90071992547410", "NaN", " 150 "]) {
    await expect(searchGrants(typed, "alpha", 20, null, null, null, null, null, null, null, null, bad))
      .rejects.toMatchObject({ code: "INVALID_PROJECT_BUDGET", status: 400 });
  }
});
