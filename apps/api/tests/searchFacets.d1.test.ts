import { afterEach, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import type { D1DatabaseLike } from "../src/env";
import { FACET_MATCH_LIMIT, searchGrants } from "../src/search";

let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

it("real D1 returns complete facets at the cap and null beyond it", async () => {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "search-facet-cap-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "search-facet-cap-test" },
  }));
  const db = await mf.getD1Database("DB");
  for (const sql of [
    "CREATE TABLE grant_search_documents (grant_call_version_id TEXT PRIMARY KEY, title TEXT, summary TEXT, status TEXT, submission_close_at TEXT)",
    "CREATE TABLE grant_call_versions (id TEXT PRIMARY KEY, grant_call_id TEXT, official_detail_url TEXT, funding_instrument_type TEXT NOT NULL DEFAULT 'GRANT', captured_at TEXT NOT NULL DEFAULT '2026-09-26T20:00:00Z', verification_status TEXT NOT NULL DEFAULT 'VERIFIED')",
    "CREATE TABLE grant_calls (id TEXT PRIMARY KEY, programme_id TEXT, current_version_id TEXT)",
    "CREATE TABLE programmes (id TEXT PRIMARY KEY, provider_id TEXT)",
    "CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT)",
    "CREATE VIRTUAL TABLE grant_search_fts USING fts5(grant_call_version_id UNINDEXED, title, summary, supported_activities, eligible_costs, keywords)",
    "INSERT INTO providers VALUES ('p', 'Test provider')",
    "INSERT INTO programmes VALUES ('pr', 'p')",
    "INSERT INTO grant_calls VALUES ('g', 'pr', 'v-0')",
    "INSERT INTO grant_call_versions (id,grant_call_id,official_detail_url,funding_instrument_type) VALUES ('v-0', 'g', NULL, 'GRANT')",
    "INSERT INTO grant_search_documents VALUES ('v-0', 'alpha grant', '', 'OPEN', NULL)",
  ]) await db.prepare(sql).run();
  const insert = db.prepare("INSERT INTO grant_search_fts(grant_call_version_id, title) VALUES (?, 'alpha grant')");
  for (let i = 0; i < FACET_MATCH_LIMIT; i += 100) {
    await db.batch(Array.from({ length: Math.min(100, FACET_MATCH_LIMIT - i) }, (_, j) =>
      insert.bind(`v-${i + j}`)));
  }
  const first = await searchGrants(db as unknown as D1DatabaseLike, "alpha");
  expect(first.facets?.status).toEqual({ OPEN: 1, PLANNED: 0, ANNOUNCED: 0 });
  expect(first.facets?.providers).toEqual([{ name: "Test provider", count: 1 }]);
  expect(first.results).toHaveLength(1);
  await db.prepare("INSERT INTO grant_search_fts(grant_call_version_id, title) VALUES ('v-over', 'alpha grant')").run();
  const over = await searchGrants(db as unknown as D1DatabaseLike, "alpha");
  expect(over.facets).toBeNull();
  expect(over.results).toHaveLength(1);
});

it("real D1 filters canonical instrument before pagination and in bounded facets", async () => {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "search-instrument-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "search-instrument-test" },
  }));
  const db = await mf.getD1Database("DB");
  for (const sql of [
    "CREATE TABLE grant_search_documents (grant_call_version_id TEXT PRIMARY KEY, title TEXT, summary TEXT, status TEXT, submission_close_at TEXT)",
    "CREATE TABLE grant_call_versions (id TEXT PRIMARY KEY, grant_call_id TEXT, official_detail_url TEXT, funding_instrument_type TEXT, captured_at TEXT NOT NULL DEFAULT '2026-09-26T20:00:00Z', verification_status TEXT NOT NULL DEFAULT 'VERIFIED')",
    "CREATE TABLE grant_calls (id TEXT PRIMARY KEY, programme_id TEXT, current_version_id TEXT)",
    "CREATE TABLE programmes (id TEXT PRIMARY KEY, provider_id TEXT)",
    "CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT)",
    "CREATE VIRTUAL TABLE grant_search_fts USING fts5(grant_call_version_id UNINDEXED, title, summary, supported_activities, eligible_costs, keywords)",
    "INSERT INTO providers VALUES ('p', 'Test provider')",
    "INSERT INTO programmes VALUES ('pr', 'p')",
  ]) await db.prepare(sql).run();
  for (const [id, instrument, status, date] of [
    ["g1", "GRANT", "OPEN", "2027-01-01T00:00:00Z"],
    ["l1", "LOAN", "OPEN", "2027-02-01T00:00:00Z"],
    ["l2", "LOAN", "PLANNED", "2027-03-01T00:00:00Z"],
  ]) {
    await db.prepare("INSERT INTO grant_calls VALUES (?, 'pr', ?)").bind(`call-${id}`, id).run();
    await db.prepare("INSERT INTO grant_call_versions (id,grant_call_id,official_detail_url,funding_instrument_type) VALUES (?, ?, NULL, ?)").bind(id, `call-${id}`, instrument).run();
    await db.prepare("INSERT INTO grant_search_documents VALUES (?, 'alpha grant', '', ?, ?)").bind(id, status, date).run();
    await db.prepare("INSERT INTO grant_search_fts(grant_call_version_id, title) VALUES (?, 'alpha grant')").bind(id).run();
  }
  for (const sort of [null, "DEADLINE", "DEADLINE_LATEST"]) {
    const first = await searchGrants(db as unknown as D1DatabaseLike, "alpha", 1, null,
      null, null, null, null, sort, null, "LOAN");
    expect(first.results).toHaveLength(1);
    expect(first.results[0].grantCallVersionId).not.toBe("g1");
    expect(first.facets?.status).toEqual({ OPEN: 1, PLANNED: 1, ANNOUNCED: 0 });
    expect(first.facets?.providers).toEqual([{ name: "Test provider", count: 2 }]);
    const second = await searchGrants(db as unknown as D1DatabaseLike, "alpha", 1, first.nextCursor,
      null, null, null, null, sort, null, "LOAN");
    expect(new Set([...first.results, ...second.results].map((r) => r.grantCallVersionId)))
      .toEqual(new Set(["l1", "l2"]));
  }
});
