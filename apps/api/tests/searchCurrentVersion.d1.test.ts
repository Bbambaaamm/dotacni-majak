import { afterEach, expect, it } from "vitest";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import type { D1DatabaseLike, Env } from "../src/env";
import { handleRequest } from "../src/index";
import { searchGrants } from "../src/search";

let mf: Miniflare | undefined;
afterEach(async () => { await mf?.dispose(); mf = undefined; });

it("real D1 search and facets only expose each call's own current version", async () => {
  mf = new Miniflare(convertV4MiniflareOptions({
    name: "search-current-version-test", modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "search-current-version-test" },
  }));
  const db = await mf.getD1Database("DB");
  for (const sql of [
    "CREATE TABLE grant_search_documents (grant_call_version_id TEXT PRIMARY KEY, title TEXT, summary TEXT, status TEXT, submission_close_at TEXT)",
    "CREATE TABLE grant_call_versions (id TEXT PRIMARY KEY, grant_call_id TEXT, official_detail_url TEXT, funding_instrument_type TEXT, captured_at TEXT NOT NULL DEFAULT '2026-11-21T00:00:00Z', verification_status TEXT NOT NULL DEFAULT 'VERIFIED')",
    "CREATE TABLE grant_calls (id TEXT PRIMARY KEY, programme_id TEXT, current_version_id TEXT)",
    "CREATE TABLE programmes (id TEXT PRIMARY KEY, provider_id TEXT)",
    "CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT)",
    "CREATE VIRTUAL TABLE grant_search_fts USING fts5(grant_call_version_id UNINDEXED, title, summary, supported_activities, eligible_costs, keywords)",
    "INSERT INTO providers VALUES ('p', 'Test provider')",
    "INSERT INTO programmes VALUES ('pr', 'p')",
    "INSERT INTO grant_calls VALUES ('a', 'pr', 'a-new')",
    "INSERT INTO grant_calls VALUES ('b', 'pr', 'b-current')",
    "INSERT INTO grant_calls VALUES ('corrupt', 'pr', 'b-current')",
  ]) await db.prepare(sql).run();
  for (const [version, call, status, date] of [
    ["a-old", "a", "OPEN", "2027-01-01T00:00:00Z"],
    ["a-new", "a", "PLANNED", "2027-02-01T00:00:00Z"],
    ["b-current", "b", "OPEN", "2027-03-01T00:00:00Z"],
    ["corrupt-old", "corrupt", "ANNOUNCED", "2027-04-01T00:00:00Z"],
  ]) {
    await db.prepare("INSERT INTO grant_call_versions (id, grant_call_id) VALUES (?, ?)").bind(version, call).run();
    await db.prepare("INSERT INTO grant_search_documents VALUES (?, 'alpha grant', '', ?, ?)").bind(version, status, date).run();
    await db.prepare("INSERT INTO grant_search_fts(grant_call_version_id, title) VALUES (?, 'alpha grant')").bind(version).run();
  }
  const typed = db as unknown as D1DatabaseLike;
  const env: Env = { DB: typed, ENVIRONMENT: "local", RAW: { head: async () => null }, SEARCH: { describe: async () => ({}) } };
  const api = await handleRequest(new Request("https://example.test/search?intent=alpha"), env);
  expect(api.status).toBe(200);
  const payload = await api.json() as { results: Array<{ grantCallVersionId: string; grantCallId: string }>; facets: { status: Record<string, number>; providers: Array<{ count: number }> } };
  expect(payload.results.map((row) => [row.grantCallVersionId, row.grantCallId])).toEqual([["a-new", "a"], ["b-current", "b"]]);
  expect(payload.facets.status).toEqual({ OPEN: 1, PLANNED: 1, ANNOUNCED: 0 });
  expect(payload.facets.providers).toEqual([{ name: "Test provider", count: 2 }]);
  for (const sort of [null, "DEADLINE", "DEADLINE_LATEST"]) {
    const first = await searchGrants(typed, "alpha", 1, null, null, null, null, null, sort);
    expect(first.results).toHaveLength(1);
    expect(first.nextCursor).not.toBeNull();
    const second = await searchGrants(typed, "alpha", 1, first.nextCursor, null, null, null, null, sort);
    expect(new Set([...first.results, ...second.results].map((row) => row.grantCallVersionId)))
      .toEqual(new Set(["a-new", "b-current"]));
    expect(second.nextCursor).toBeNull();
  }
});
