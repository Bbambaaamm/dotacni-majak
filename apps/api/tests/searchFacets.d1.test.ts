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
    "CREATE TABLE grant_call_versions (id TEXT PRIMARY KEY, grant_call_id TEXT, official_detail_url TEXT)",
    "CREATE TABLE grant_calls (id TEXT PRIMARY KEY, programme_id TEXT)",
    "CREATE TABLE programmes (id TEXT PRIMARY KEY, provider_id TEXT)",
    "CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT)",
    "CREATE VIRTUAL TABLE grant_search_fts USING fts5(grant_call_version_id UNINDEXED, title, summary, supported_activities, eligible_costs, keywords)",
    "INSERT INTO providers VALUES ('p', 'Test provider')",
    "INSERT INTO programmes VALUES ('pr', 'p')",
    "INSERT INTO grant_calls VALUES ('g', 'pr')",
    "INSERT INTO grant_call_versions VALUES ('v-0', 'g', NULL)",
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
