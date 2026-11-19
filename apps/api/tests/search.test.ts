import { describe, expect, it } from "vitest";
import type { D1DatabaseLike, D1PreparedStatementLike } from "../src/env";
import { searchGrants } from "../src/search";

type Row = { grant_call_version_id: string; grant_call_id: string; title: string;
  summary: string; status: string; submission_close_at: null; provider_name: string;
  official_detail_url: null; rank: number };

function row(id: number, rank = 0): Row {
  return { grant_call_version_id: `v-${String(id).padStart(3, "0")}`,
    grant_call_id: `g-${id}`, title: `Grant ${id}`, summary: "", status: "OPEN",
    submission_close_at: null, provider_name: "Provider", official_detail_url: null, rank };
}

function database(direct: Row[], expanded: Row[], empty = false): D1DatabaseLike {
  return {
    prepare(sql: string): D1PreparedStatementLike {
      let values: unknown[] = [];
      const statement: D1PreparedStatementLike = {
        bind(...args) { values = args; return statement; },
        async first<T>() { return { count: empty ? 0 : 1 } as T; },
        async all<T>() {
          const ontology = sql.includes("NOT IN");
          expect(sql).toContain("ORDER BY rank ASC, grant_call_version_id ASC");
          const candidates = (ontology ? expanded.filter((r) => !direct.some((d) => d.grant_call_version_id === r.grant_call_version_id)) : direct)
            .slice().sort((a, b) => a.rank - b.rank || a.grant_call_version_id.localeCompare(b.grant_call_version_id));
          const after = sql.includes("WHERE rank > ?") ? values.slice(-4, -1) : null;
          const filtered = after ? candidates.filter((r) => r.rank > Number(after[0]) ||
            (r.rank === Number(after[0]) && r.grant_call_version_id > String(after[2]))) : candidates;
          return { success: true, results: filtered.slice(0, Number(values.at(-1))) as T[] };
        },
        async run<T>() { return { success: true, results: [] as T[] }; },
      };
      return statement;
    },
    async batch() { return []; },
  };
}

describe("search cursor", () => {
  it("walks over 20 direct rows with stable rank/id ties and repeatable cursors", async () => {
    const db = database(Array.from({ length: 27 }, (_, i) => row(i + 1, Math.floor(i / 3))), []);
    const first = await searchGrants(db, "  arbitrary   intent ");
    expect(first.results).toHaveLength(20);
    expect(first.nextCursor).toBeTruthy();
    const second = await searchGrants(db, "arbitrary intent", 20, first.nextCursor);
    expect(second.results).toHaveLength(7);
    expect(second.nextCursor).toBeNull();
    expect(new Set([...first.results, ...second.results].map((r) => r.grantCallVersionId)).size).toBe(27);
    expect(await searchGrants(db, "arbitrary intent", 20, first.nextCursor)).toEqual(second);
  });

  it("crosses direct to ontology and removes direct matches from every ontology page", async () => {
    const direct = Array.from({ length: 21 }, (_, i) => row(i + 1));
    const expanded = [direct[0], ...Array.from({ length: 25 }, (_, i) => row(i + 100))];
    const db = database(direct, expanded);
    let cursor: string | null = null;
    const all = [];
    do {
      const page = await searchGrants(db, "koupaliště", 20, cursor);
      all.push(...page.results);
      cursor = page.nextCursor;
    } while (cursor);
    expect(all).toHaveLength(46);
    expect(all.slice(0, 21).every((r) => r.matchKind === "DIRECT")).toBe(true);
    expect(all.slice(21).every((r) => r.matchKind === "ONTOLOGY")).toBe(true);
    expect(new Set(all.map((r) => r.grantCallVersionId)).size).toBe(46);
  });

  it("validates cursors and page size before database access", async () => {
    const db = database(Array.from({ length: 3 }, (_, i) => row(i)), []);
    const first = await searchGrants(db, "koupaliště", 1);
    await expect(searchGrants(db, "other", 1, first.nextCursor)).rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 2, first.nextCursor)).rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 1, "not-a-cursor")).rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 51)).rejects.toMatchObject({ code: "INVALID_LIMIT" });
  });

  it("round-trips a cursor for the longest accepted multibyte intent", async () => {
    const intent = `strankovani${"—".repeat(489)}`;
    const db = database([row(1), row(2)], []);
    const first = await searchGrants(db, intent, 1);
    expect(first.nextCursor?.length).toBeGreaterThan(2048);
    expect((await searchGrants(db, intent, 1, first.nextCursor)).results).toEqual([
      expect.objectContaining({ grantCallVersionId: "v-002" }),
    ]);
  });

  it("reports empty index and propagates database errors", async () => {
    expect(await searchGrants(database([], [], true), "koupaliště")).toMatchObject({
      results: [], indexState: "EMPTY", nextCursor: null,
    });
    const db = database([], []);
    db.prepare = () => { throw new Error("database down"); };
    await expect(searchGrants(db, "koupaliště")).rejects.toThrow("database down");
  });
});
