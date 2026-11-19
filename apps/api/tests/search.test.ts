import { describe, expect, it } from "vitest";
import type { D1DatabaseLike, D1PreparedStatementLike } from "../src/env";
import { searchGrants } from "../src/search";

type Row = { grant_call_version_id: string; grant_call_id: string; title: string;
  summary: string; status: string; submission_close_at: string | null; provider_name: string;
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
          if (sql.startsWith("WITH matched AS MATERIALIZED")) return { success: true, results: [] as T[] };
          const ontology = sql.includes("NOT IN");
          expect(sql).toContain("ORDER BY rank ASC, grant_call_version_id ASC");
          expect(sql).toContain("d.status IN (?, ?, ?)");
          const selectedStatus = sql.includes("AND d.status = ?") ? values[4] : null;
          const provider = sql.includes("AND p.name = ?") ? values[4 + Number(Boolean(selectedStatus))] : null;
          const deadline = sql.includes("AND d.submission_close_at IS NOT NULL") ? "KNOWN" :
            sql.includes("AND d.submission_close_at IS NULL") ? "UNKNOWN" : null;
          const dateIndex = 4 + Number(Boolean(selectedStatus)) + Number(Boolean(provider));
          const closesFrom = sql.includes("AND date(d.submission_close_at) >= ?") ? String(values[dateIndex]) : null;
          const closesBy = sql.includes("AND date(d.submission_close_at) <= ?") ?
            String(values[dateIndex + Number(Boolean(closesFrom))]) : null;
          const candidates = (ontology ? expanded.filter((r) => !direct.some((d) => d.grant_call_version_id === r.grant_call_version_id)) : direct)
            .filter((r) => ["OPEN", "PLANNED", "ANNOUNCED"].includes(r.status) &&
              (!selectedStatus || r.status === selectedStatus) &&
              (!provider || r.provider_name === provider) &&
              (!deadline || (r.submission_close_at === null) === (deadline === "UNKNOWN")) &&
              (!(closesFrom || closesBy) || (r.submission_close_at !== null &&
                Number.isFinite(Date.parse(r.submission_close_at)) &&
                (!closesFrom || new Date(r.submission_close_at).toISOString().slice(0, 10) >= closesFrom) &&
                (!closesBy || new Date(r.submission_close_at).toISOString().slice(0, 10) <= closesBy))))
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
  it("binds facet inputs and reports a bounded provider list without a total", async () => {
    const statements: { sql: string; values: unknown[] }[] = [];
    const db: D1DatabaseLike = {
      prepare(sql) {
        const entry = { sql, values: [] as unknown[] };
        statements.push(entry);
        const statement: D1PreparedStatementLike = {
          bind(...values) { entry.values = values; return statement; },
          async first<T>() { return { count: 1 } as T; },
          async all<T>() {
            if (sql.includes("SELECT provider_name AS name")) return { success: true,
              results: Array.from({ length: 21 }, (_, i) => ({ name: `Provider ${i}`, count: 1 })) as T[] };
            if (sql.startsWith("WITH matched AS MATERIALIZED")) return { success: true,
              results: [{ kind: "status", value: "OPEN", count: 3 },
                { kind: "deadline", value: "UNKNOWN", count: 2 }] as T[] };
            return { success: true, results: [] as T[] };
          },
          async run<T>() { return { success: true, results: [] as T[] }; },
        };
        return statement;
      },
      async batch() { return []; },
    };
    const provider = "Provider ' OR 1=1 --";
    const result = await searchGrants(db, "koupaliště", 1, null, "OPEN", "UNKNOWN", provider);
    expect(result.facets).toMatchObject({ status: { OPEN: 3 }, deadline: { UNKNOWN: 2 },
      providersTruncated: true });
    expect(result.facets.providers).toHaveLength(20);
    const facetStatements = statements.filter(({ sql }) => sql.startsWith("WITH matched AS MATERIALIZED"));
    expect(facetStatements).toHaveLength(2);
    expect(facetStatements.every(({ sql }) => !sql.includes(provider))).toBe(true);
    expect(facetStatements[0].values).toContain(provider);
    expect(facetStatements[1].values.at(-1)).toBe(21);
  });
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

  it("filters both phases before pagination and binds status to cursors", async () => {
    const direct = Array.from({ length: 24 }, (_, i) => row(i + 1, i));
    direct.push({ ...row(25, 25), status: "PLANNED" }, { ...row(26, 26), status: "CLOSED" });
    const expanded = [{ ...row(100, 0), status: "PLANNED" }, direct[24], { ...row(101, 1), status: "CLOSED" }];
    const db = database(direct, expanded);
    const unfiltered = await searchGrants(db, "koupaliště", 50);
    expect(unfiltered.results).toHaveLength(26);
    expect(unfiltered.results.every((result) => result.status !== "CLOSED")).toBe(true);
    const planned = await searchGrants(db, "koupaliště", 1, null, "PLANNED");
    expect(planned.results.map((r) => r.grantCallVersionId)).toEqual(["v-025"]);
    expect(planned.nextCursor).toBeTruthy();
    const continuation = await searchGrants(db, "koupaliště", 1, planned.nextCursor, "PLANNED");
    expect(continuation.results).toEqual([expect.objectContaining({ grantCallVersionId: "v-100", matchKind: "ONTOLOGY" })]);
    await expect(searchGrants(db, "koupaliště", 1, planned.nextCursor, "OPEN")).rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 1, planned.nextCursor)).rejects.toMatchObject({ code: "INVALID_CURSOR" });
    for (const status of ["CLOSED", "", "open", "ALL", "PLANNED "]) {
      await expect(searchGrants(db, "koupaliště", 1, null, status)).rejects.toMatchObject({ code: "INVALID_STATUS" });
    }
  });

  it("filters known and missing deadlines across both phases before pagination, binding the cursor", async () => {
    const direct = Array.from({ length: 24 }, (_, i) => row(i + 1, i));
    direct[22] = { ...direct[22], submission_close_at: "2027-05-01T00:00:00Z" };
    const expanded = [{ ...row(100), submission_close_at: "2027-07-01T00:00:00Z" }, row(101)];
    const db = database(direct, expanded);
    const first = await searchGrants(db, "koupaliště", 1, null, null, "KNOWN");
    expect(first.results.map((r) => r.grantCallVersionId)).toEqual(["v-023"]);
    expect(first.nextCursor).toBeTruthy();
    const second = await searchGrants(db, "koupaliště", 1, first.nextCursor, null, "KNOWN");
    expect(second.results).toEqual([expect.objectContaining({ grantCallVersionId: "v-100", matchKind: "ONTOLOGY" })]);
    expect(second.nextCursor).toBeNull();
    const unknown = await searchGrants(db, "koupaliště", 50, null, null, "UNKNOWN");
    expect(unknown.results).toHaveLength(24);
    expect(unknown.results.every((result) => result.submissionCloseAt === null)).toBe(true);
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor, null, "UNKNOWN"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    for (const deadline of ["ALL", "", "known", "KNOWN ", "OVERDUE"]) {
      await expect(searchGrants(db, "koupaliště", 1, null, null, deadline))
        .rejects.toMatchObject({ code: "INVALID_DEADLINE" });
    }
  });

  it("filters providers before both FTS phases and binds the exact name to a cursor", async () => {
    const direct = Array.from({ length: 23 }, (_, i) => row(i + 1, i));
    direct[21] = { ...direct[21], provider_name: "Provider B" };
    const expanded = [{ ...row(100), provider_name: "Provider B" }, row(101)];
    const db = database(direct, expanded);
    const first = await searchGrants(db, "koupaliště", 1, null, null, null, "Provider B");
    expect(first.results.map((result) => result.grantCallVersionId)).toEqual(["v-022"]);
    expect(first.nextCursor).toBeTruthy();
    const second = await searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, "Provider B");
    expect(second.results).toEqual([expect.objectContaining({ grantCallVersionId: "v-100", matchKind: "ONTOLOGY" })]);
    expect(second.nextCursor).toBeNull();
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, "Provider"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    for (const provider of ["", " Provider B", "Provider B ", "x".repeat(201), "bad\nname"]) {
      await expect(searchGrants(db, "koupaliště", 1, null, null, null, provider))
        .rejects.toMatchObject({ code: "INVALID_PROVIDER" });
    }
  });

  it("filters inclusive UTC deadline dates globally before pagination and binds the cursor", async () => {
    const direct: Row[] = Array.from({ length: 24 }, (_, i) => ({ ...row(i + 1, i),
      submission_close_at: i === 21 ? "2027-03-31T23:59:59Z" : "2027-04-01T00:00:00Z" }));
    direct[23] = { ...direct[23], submission_close_at: null };
    const expanded = [{ ...row(100), submission_close_at: "2027-03-30T10:00:00Z" },
      { ...row(101), submission_close_at: "2027-04-01T00:00:00Z" }];
    const db = database(direct, expanded);
    const first = await searchGrants(db, "koupaliště", 1, null, null, null, null, "2027-03-31");
    expect(first.results.map((r) => r.grantCallVersionId)).toEqual(["v-022"]);
    expect(first.nextCursor).toBeTruthy();
    const second = await searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null, "2027-03-31");
    expect(second.results).toEqual([expect.objectContaining({ grantCallVersionId: "v-100", matchKind: "ONTOLOGY" })]);
    expect(second.nextCursor).toBeNull();
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null, "2027-04-01"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    expect((await searchGrants(db, "koupaliště", 50, null, null, "UNKNOWN", null, "2027-03-31")).results)
      .toEqual([]);
    for (const invalid of ["", "2027-02-29", "2027-3-1", "2027-03-31 ", "2027-03-31T00:00:00Z"]) {
      await expect(searchGrants(db, "koupaliště", 1, null, null, null, null, invalid))
        .rejects.toMatchObject({ code: "INVALID_CLOSES_BY" });
    }
  });

  it("filters an inclusive start across direct and ontology pages and binds both bounds", async () => {
    const direct = Array.from({ length: 23 }, (_, i) => ({ ...row(i + 1, i),
      submission_close_at: i === 21 ? "2027-05-01T00:00:00Z" : "2027-04-30T23:59:59Z" }));
    const expanded = [{ ...row(100), submission_close_at: "2027-05-31T23:59:59Z" },
      { ...row(101), submission_close_at: "2027-06-01T00:00:00Z" },
      { ...row(102), submission_close_at: "31.05.2027" }, row(103)];
    const db = database(direct, expanded);
    const first = await searchGrants(db, "koupaliště", 1, null, null, null, null, "2027-05-31", null, "2027-05-01");
    expect(first.results.map((r) => r.grantCallVersionId)).toEqual(["v-022"]);
    const second = await searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null, "2027-05-31", null, "2027-05-01");
    expect(second.results).toEqual([expect.objectContaining({ grantCallVersionId: "v-100", matchKind: "ONTOLOGY" })]);
    expect(second.nextCursor).toBeNull();
    for (const from of [null, "2027-05-02"]) {
      await expect(searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null, "2027-05-31", null, from))
        .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    }
    await expect(searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null, "2027-06-01", null, "2027-05-01"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
  });

  it("rejects invalid starts and reversed ranges before touching D1", async () => {
    const db = database([], []);
    db.prepare = () => { throw new Error("D1 was touched"); };
    for (const value of ["", "2027-02-29", "2027-5-01", "2027-05-01T00:00:00Z"]) {
      await expect(searchGrants(db, "test", 20, null, null, null, null, null, null, value))
        .rejects.toMatchObject({ code: "INVALID_CLOSES_FROM", status: 400 });
    }
    await expect(searchGrants(db, "test", 20, null, null, null, null, "2027-04-30", null, "2027-05-01"))
      .rejects.toMatchObject({ code: "INVALID_DEADLINE_RANGE", status: 400 });
  });

  it("applies both bounds in both date-sorted FTS phases before cursor paging", async () => {
    for (const sort of ["DEADLINE", "DEADLINE_LATEST"] as const) {
      let calls = 0;
      const db: D1DatabaseLike = {
        prepare(sql) {
          let values: unknown[] = [];
          const statement: D1PreparedStatementLike = {
            bind(...args) { values = args; return statement; },
            async first<T>() { return { count: 1 } as T; },
            async all<T>() {
              if (sql.startsWith("WITH matched AS MATERIALIZED")) return { success: true, results: [] as T[] };
              expect(sql).toContain("WITH matches AS");
              expect(sql.match(/AND date\(d\.submission_close_at\) >= \?/g)).toHaveLength(2);
              expect(sql.match(/AND date\(d\.submission_close_at\) <= \?/g)).toHaveLength(2);
              expect(values.filter((v) => v === "2027-05-01")).toHaveLength(2);
              expect(values.filter((v) => v === "2027-05-31")).toHaveLength(2);
              expect(sql.indexOf("WITH matches AS")).toBeLessThan(sql.indexOf("ORDER BY (close_sort IS NULL)"));
              calls++;
              const rows = [
                { ...row(1), submission_close_at: "2027-05-01T00:00:00Z", close_sort: 2461526.5, match_phase: 0 },
                { ...row(2), submission_close_at: "2027-05-31T23:59:59Z", close_sort: 2461557.5, match_phase: 1 },
              ];
              return { success: true, results: (calls === 1 ? rows : rows.slice(1)) as T[] };
            },
            async run<T>() { return { success: true, results: [] as T[] }; },
          };
          return statement;
        },
        async batch() { return []; },
      };
      const first = await searchGrants(db, "koupaliště", 1, null, null, null, null,
        "2027-05-31", sort, "2027-05-01");
      expect(first.nextCursor).toBeTruthy();
      const second = await searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null,
        "2027-05-31", sort, "2027-05-01");
      expect(second.results).toHaveLength(1);
      await expect(searchGrants(db, "koupaliště", 1, first.nextCursor, null, null, null,
        "2027-05-31", sort, "2027-05-02")).rejects.toMatchObject({ code: "INVALID_CURSOR" });
    }
  });

  it("preserves a non-NULL but unparseable source deadline when sorting", async () => {
    const invalid = { ...row(1), submission_close_at: "31.12.2027", close_sort: null, match_phase: 0 };
    const db: D1DatabaseLike = {
      prepare(sql) {
        const statement: D1PreparedStatementLike = {
          bind() { return statement; },
          async first<T>() { return { count: 1 } as T; },
          async all<T>() {
            if (sql.startsWith("WITH matched AS MATERIALIZED")) return { success: true, results: [] as T[] };
            expect(sql).toContain("julianday(d.submission_close_at) AS close_sort");
            return { success: true, results: [invalid] as T[] };
          },
          async run<T>() { return { success: true, results: [] as T[] }; },
        };
        return statement;
      },
      async batch() { return []; },
    };
    const result = await searchGrants(db, "strankovani", 20, null, null, "KNOWN", null, null, "DEADLINE");
    expect(result.results).toEqual([expect.objectContaining({ submissionCloseAt: "31.12.2027" })]);
  });

  it("rejects invalid sort values and cannot reuse a relevance cursor for date order", async () => {
    const db = database([row(1), row(2)], []);
    const first = await searchGrants(db, "strankovani", 1);
    for (const invalid of ["", "UNKNOWN", "DEADLINE ", "deadline", "ASC"]) {
      await expect(searchGrants(db, "strankovani", 1, null, null, null, null, null, invalid))
        .rejects.toMatchObject({ code: "INVALID_SORT" });
    }
    await expect(searchGrants(db, "strankovani", 1, first.nextCursor, null, null, null, null, "DEADLINE"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
  });

  it("continues a pre-cutoff cursor when no cutoff is selected, but never under a cutoff", async () => {
    const db = database([row(1), row(2)], []);
    const first = await searchGrants(db, "strankovani", 1);
    const legacy = JSON.parse(atob(first.nextCursor!)) as Record<string, unknown>;
    delete legacy.closesBy;
    delete legacy.closesFrom;
    const oldCursor = btoa(JSON.stringify(legacy)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
    expect((await searchGrants(db, "strankovani", 1, oldCursor)).results.map((r) => r.grantCallVersionId))
      .toEqual(["v-002"]);
    await expect(searchGrants(db, "strankovani", 1, oldCursor, null, null, null, "2027-03-31"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
    await expect(searchGrants(db, "strankovani", 1, oldCursor, null, null, null, null, null, "2027-03-01"))
      .rejects.toMatchObject({ code: "INVALID_CURSOR" });
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
