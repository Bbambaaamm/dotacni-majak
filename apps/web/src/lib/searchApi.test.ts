import { afterEach, describe, expect, it, vi } from "vitest";

import { searchErrorMessage, searchGrants } from "./searchApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("search API client", () => {
  it("fails closed on malformed successful responses instead of showing false results", async () => {
    const valid = { intent: "alpha", results: [], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    for (const body of [null, [], { ...valid, intent: "other" },
      { ...valid, results: null }, { ...valid, nextCursor: undefined },
      { ...valid, nextCursor: "" },
      { ...valid, facets: undefined }, { ...valid, facets: { providers: [] } },
      { ...valid, results: [{ title: "partial" }] }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not-json", { status: 200 })));
    await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
  });

  it("rejects contradictory index state and unrenderable result identities/status", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const valid = { intent: "alpha", expandedTerms: [], indexState: "READY", nextCursor: null,
      facets: null, results: [result] };
    for (const change of [{ capturedAt: undefined }, { capturedAt: "2026-02-30T20:00:00Z" },
      { capturedAt: "not-a-date" }, { verificationStatus: undefined },
      { verificationStatus: "RECHECKED_TODAY" }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...valid,
        results: [{ ...result, ...change }] }), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    }
    for (const body of [
      { ...valid, indexState: "EMPTY" },
      { ...valid, indexState: "EMPTY", results: [], nextCursor: "more" },
      ...[
        { grantCallVersionId: "" }, { grantCallVersionId: "  " },
        { grantCallId: "" }, { grantCallId: "\t" }, { title: "  " },
        { providerName: "  " }, { status: "CANCELLED" }, { status: "UNVERIFIED" },
      ].map((change) => ({ ...valid, results: [{ ...result, ...change }] })),
    ]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...valid,
      indexState: "EMPTY", results: [], nextCursor: null,
      facets: { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [], providersTruncated: false } }), { status: 200 })));
    expect((await searchGrants("alpha")).indexState).toBe("EMPTY");
  });

  it("rejects an ontology explanation without expanded search terms on either page", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "ONTOLOGY" };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    for (const terms of [[], [" "]]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
        ...body, expandedTerms: terms,
      }), { status: 200 })));
      for (const cursor of [undefined, "page-2"]) {
        await expect(searchGrants("alpha", undefined, cursor)).rejects.toMatchObject({
          code: "INVALID_SEARCH_RESPONSE", status: 200,
        });
      }
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      ...body, expandedTerms: ["širší pojem"],
    }), { status: 200 })));
    expect((await searchGrants("alpha")).results).toEqual([result]);
    const continuation = (expected: string[]) => searchGrants("alpha", undefined, "page-2",
      undefined, undefined, undefined, undefined, undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, expected);
    await expect(continuation([])).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    await expect(continuation(["jiný pojem"])).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    expect((await continuation(["širší pojem"])).results).toEqual([result]);
  });

  it("rejects a direct relevance match after an ontology match on either page", async () => {
    const direct = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const ontology = { ...direct, grantCallVersionId: "v2", grantCallId: "g2", matchKind: "ONTOLOGY" };
    const body = { intent: "alpha", results: [ontology, direct], expandedTerms: ["širší pojem"],
      indexState: "READY", nextCursor: null, facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    const continuation = (sort?: "RELEVANCE" | "DEADLINE", previous?: "DIRECT" | "ONTOLOGY") =>
      searchGrants("alpha", undefined, "page-2", undefined, undefined, undefined, undefined,
        sort, undefined, undefined, undefined, undefined, undefined, undefined, undefined, previous);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, results: [direct] }), { status: 200 })));
    await expect(continuation("RELEVANCE", "ONTOLOGY"))
      .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    expect((await continuation("RELEVANCE", "DIRECT")).results).toEqual([direct]);
    // Global date order may interleave match phases; its API contract is distinct.
    expect((await continuation("DEADLINE", "ONTOLOGY")).results).toEqual([direct]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, results: [direct, ontology] }), { status: 200 })));
    expect((await searchGrants("alpha")).results).toEqual([direct, ontology]);
    expect((await continuation("DEADLINE", "ONTOLOGY")).results).toEqual([direct, ontology]);
  });

  it("rejects facet counts that contradict visible results, without treating unavailable counts as zero", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const facets = { status: { OPEN: 1, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 1 }, providers: [{ name: "Obec", count: 1 }],
      providersTruncated: false };
    const valid = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets };
    for (const invalid of [
      { ...valid, facets: { ...facets, status: { ...facets.status, OPEN: 0 } } },
      { ...valid, facets: { ...facets, deadline: { ...facets.deadline, UNKNOWN: 0 } } },
      { ...valid, facets: { ...facets, providers: [{ name: "Obec", count: 0 }] } },
      { ...valid, facets: { ...facets, providers: [] } },
      { ...valid, results: [result, { ...result, grantCallVersionId: "v2", grantCallId: "g2" }] },
    ]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(invalid), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    }
    for (const accepted of [valid, { ...valid, facets: null },
      { ...valid, facets: { ...facets, providers: [], providersTruncated: true } }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(accepted), { status: 200 })));
      expect((await searchGrants("alpha")).results).toEqual([result]);
    }
  });

  it("rejects contradictory status and deadline facet totals when neither is filtered", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const facets = { status: { OPEN: 2, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 1 }, providers: [{ name: "Obec", count: 1 }],
      providersTruncated: false };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets };
    for (const invalid of [facets, { ...facets, deadline: { ...facets.deadline, OTHER: 1 } }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: invalid }), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    }
    // A selected status changes the population behind the deadline facet.
    expect((await searchGrants("alpha", undefined, undefined, "OPEN")).results).toEqual([result]);
    // Unavailable counts remain unknown, never interpreted as zero.
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: null }), { status: 200 })));
    expect((await searchGrants("alpha")).results).toEqual([result]);
  });

  it("checks complete provider counts against the comparable unfiltered facet population", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const facets = { status: { OPEN: 2, PLANNED: 1, ANNOUNCED: 0 },
      deadline: { KNOWN: 1, UNKNOWN: 2 }, providers: [{ name: "Obec", count: 1 }],
      providersTruncated: false };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets };
    const request = (filters: { status?: "OPEN"; deadline?: "UNKNOWN"; provider?: string } = {}) =>
      searchGrants("alpha", undefined, undefined, filters.status, filters.deadline, filters.provider);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    // Without a provider filter the three complete facet populations must agree.
    await expect(request()).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    // Selecting a status leaves the deadline facet comparable to providers.
    const statusFacets = { ...facets, deadline: { KNOWN: 0, UNKNOWN: 2 } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: statusFacets }), { status: 200 })));
    await expect(request({ status: "OPEN" })).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    // Selecting a deadline leaves the status facet comparable to providers.
    const deadlineFacets = { ...facets, status: { OPEN: 2, PLANNED: 0, ANNOUNCED: 0 } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: deadlineFacets }), { status: 200 })));
    await expect(request({ deadline: "UNKNOWN" })).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    // An active provider filter changes the status/deadline populations; both
    // filters together likewise have no comparable facet population.
    const providerFacets = { ...facets, status: { OPEN: 2, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 2 } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: providerFacets }), { status: 200 })));
    expect((await request({ provider: "Obec" })).results).toHaveLength(1);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: deadlineFacets }), { status: 200 })));
    expect((await request({ status: "OPEN", deadline: "UNKNOWN" })).results).toHaveLength(1);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
      facets: { ...facets, providersTruncated: true },
    }), { status: 200 })));
    expect((await request()).results).toHaveLength(1);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
      facets: { ...facets, providers: [{ name: "Obec", count: 4 }], providersTruncated: true },
    }), { status: 200 })));
    await expect(request()).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: null }), { status: 200 })));
    expect((await request()).results).toHaveLength(1);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
      facets: { ...facets, providers: [{ name: "Obec", count: 3 }] },
    }), { status: 200 })));
    expect((await request()).results).toHaveLength(1);
  });

  it("rejects successful pages that contradict applied status, deadline or exact provider filters", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    for (const cursor of [undefined, "next-page"]) {
      await expect(searchGrants("alpha", undefined, cursor, "PLANNED"))
        .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
      await expect(searchGrants("alpha", undefined, cursor, undefined, "KNOWN"))
        .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
      await expect(searchGrants("alpha", undefined, cursor, undefined, undefined, "Jiná obec"))
        .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
      expect((await searchGrants("alpha", undefined, cursor, "OPEN", "UNKNOWN", "Obec")).results)
        .toEqual([result]);
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
      results: [{ ...result, submissionCloseAt: "2027-01-01" }],
    }), { status: 200 })));
    await expect(searchGrants("alpha", undefined, undefined, undefined, "UNKNOWN"))
      .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    expect((await searchGrants("alpha", undefined, undefined, undefined, "KNOWN")).results).toHaveLength(1);
  });

  it("rejects result dates outside an applied inclusive window on initial and continuation pages", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: "2027-05-01T23:59:00+02:00", providerName: "Obec",
      officialDetailUrl: null, capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    for (const cursor of [undefined, "page-2"]) {
      for (const submissionCloseAt of [null, "2027-04-30", "2027-06-01T00:00:00Z",
        "2027-05-01T00:30:00+02:00", "2027-02-30", "2027-05-01T99:99:99Z", "not-a-date"]) {
        vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
          results: [{ ...result, submissionCloseAt }],
        }), { status: 200 })));
        await expect(searchGrants("alpha", undefined, cursor, undefined, undefined, undefined,
          "2027-05-31", undefined, "2027-05-01")).rejects.toMatchObject({
          code: "INVALID_SEARCH_RESPONSE", status: 200,
        });
      }
      for (const submissionCloseAt of ["2027-05-01", "2027-05-01T12:00:00z",
        "2027-05-01T12:00:00Z ", "2027-05-01T12:00:00 Z",
        "2027-05-31T23:59:00+02:00", "2027-04-30T23:30:00-02:00"]) {
        vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
          results: [{ ...result, submissionCloseAt }],
        }), { status: 200 })));
        expect((await searchGrants("alpha", undefined, cursor, undefined, undefined, undefined,
          "2027-05-31", undefined, "2027-05-01")).results[0].submissionCloseAt).toBe(submissionCloseAt);
      }
    }
    // A date-only upper or lower bound also works independently.
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    await expect(searchGrants("alpha", undefined, undefined, undefined, undefined, undefined,
      "2027-04-30")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    await expect(searchGrants("alpha", undefined, undefined, undefined, undefined, undefined,
      undefined, undefined, "2027-05-02")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    expect((await searchGrants("alpha")).results).toHaveLength(1);
  });

  it("keeps SQLite's 24:00:00Z source day inside an inclusive UTC window", async () => {
    const result = { grantCallVersionId: "v24", grantCallId: "g24", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: "2027-05-01T24:00:00Z", providerName: "Obec",
      officialDetailUrl: null, capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    for (const submissionCloseAt of ["2027-05-01T24:00:00Z", "2027-05-01T24:00:00.001Z",
      "2027-05-01T24:00:00+00:00", "2027-05-01T24:59:59+02:00"]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
        results: [{ ...result, submissionCloseAt }],
      }), { status: 200 })));
      expect((await searchGrants("alpha", undefined, undefined, undefined, undefined, undefined,
        "2027-05-01", undefined, "2027-05-01")).results).toHaveLength(1);
    }
    for (const submissionCloseAt of ["2027-05-01T24:00:00-02:00",
      "2027-05-01T24:01:00+00:01"]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
        results: [{ ...result, submissionCloseAt }],
      }), { status: 200 })));
      await expect(searchGrants("alpha", undefined, undefined, undefined, undefined, undefined,
        "2027-05-01", undefined, "2027-05-01")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    }
  });

  it("rejects positive facet counts for an empty index rather than claiming it contains no calls", async () => {
    const zero = { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [], providersTruncated: false };
    const body = { intent: "alpha", results: [], expandedTerms: [],
      indexState: "EMPTY", nextCursor: null, facets: zero };
    for (const facets of [
      null, // The initial empty-index API contract always returns explicit zero counts.
      { ...zero, status: { ...zero.status, OPEN: 1 } },
      { ...zero, deadline: { ...zero.deadline, UNKNOWN: 1 } },
      { ...zero, providers: [{ name: "Obec", count: 1 }] },
      { ...zero, providersTruncated: true },
    ]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets }), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).indexState).toBe("EMPTY");
  });

  it("rejects duplicate, empty, or nonpositive provider facets before rendering filters", async () => {
    const facets = { status: { OPEN: 2, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 2 }, providers: [{ name: "Obec", count: 2 }],
      providersTruncated: false };
    const body = { intent: "alpha", results: [], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets };
    for (const providers of [
      [{ name: "Obec", count: 2 }, { name: "Obec", count: 1 }],
      [{ name: "", count: 1 }], [{ name: "  ", count: 1 }],
      [{ name: "Obec", count: 0 }],
      Array.from({ length: 21 }, (_, i) => ({ name: `Poskytovatel ${i}`, count: 1 })),
    ]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
        ...body, facets: { ...facets, providers },
      }), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({
        code: "INVALID_SEARCH_RESPONSE", status: 200,
      });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).facets?.providers).toEqual(facets.providers);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      ...body, facets: { ...facets, status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [] },
    }), { status: 200 })));
    expect((await searchGrants("alpha")).facets?.providers).toEqual([]);
  });

  it("rejects provider facets outside API count-descending, SQLite name-ascending order", async () => {
    const facets = { status: { OPEN: 7, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 7 } };
    const providers = [{ name: "Alfa", count: 3 }, { name: "Beta", count: 2 },
      { name: "\uE000", count: 1 }, { name: "\u{10000}", count: 1 }];
    const body = { intent: "alpha", results: [], expandedTerms: [], indexState: "READY",
      nextCursor: null, facets: { ...facets, providers, providersTruncated: true } };
    for (const changed of [
      [providers[1], providers[0], ...providers.slice(2)],
      [providers[0], providers[1], providers[3], providers[2]],
    ]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body,
        facets: { ...body.facets, providers: changed },
      }), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE" });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).facets?.providers).toEqual(providers);
  });

  it("rejects an oversized page on initial search and continuation, while accepting the 20-card boundary", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const cards = Array.from({ length: 21 }, (_, i) => ({ ...result,
      grantCallVersionId: `v${i}`, grantCallId: `g${i}` }));
    const body = { intent: "alpha", results: cards, expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    for (const cursor of [undefined, "page-2"]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
      await expect(searchGrants("alpha", undefined, cursor)).rejects.toMatchObject({
        code: "INVALID_SEARCH_RESPONSE", status: 200,
      });
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
        ...body, results: cards.slice(0, 20), nextCursor: cursor ? null : "page-2",
      }), { status: 200 })));
      expect((await searchGrants("alpha", undefined, cursor)).results).toHaveLength(20);
    }
  });

  it("rejects repeated version identities within and across pages without advancing pagination", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const response = { intent: "alpha", results: [result, result], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(response), { status: 200 })));
    await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    const second = { ...response, results: [result] };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(second), { status: 200 })));
    await expect(searchGrants("alpha", undefined, "cursor", undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, new Set(["v1"]))).rejects.toMatchObject({
      code: "INVALID_SEARCH_RESPONSE", status: 200,
    });
    expect((await searchGrants("alpha", undefined, "cursor", undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, new Set(["other"]))).results).toEqual([result]);
  });

  it("rejects two versions of one call within or across pages", async () => {
    const first = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const newer = { ...first, grantCallVersionId: "v2" };
    const response = { intent: "alpha", results: [first, newer], expandedTerms: [],
      indexState: "READY", nextCursor: null, facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(response), { status: 200 })));
    await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...response, results: [newer] }), { status: 200 })));
    await expect(searchGrants("alpha", undefined, "cursor", undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, new Set(["v1"]), new Set(["g1"])))
      .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    expect((await searchGrants("alpha", undefined, "cursor", undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, new Set(["v1"]), new Set(["other"]))).results)
      .toEqual([newer]);
  });

  it("rejects facet counts on a cursor page without replacing initial-page counts", async () => {
    const result = { grantCallVersionId: "v2", grantCallId: "g2", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const body = { intent: "alpha", results: [result], expandedTerms: [], indexState: "READY",
      nextCursor: null, facets: { status: { OPEN: 99, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 99 }, providers: [{ name: "Obec", count: 99 }],
        providersTruncated: false } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).facets).toEqual(body.facets);
    await expect(searchGrants("alpha", undefined, "page-2"))
      .rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, facets: null }), { status: 200 })));
    expect((await searchGrants("alpha", undefined, "page-2")).results).toEqual([result]);
  });

  it("rejects an empty READY page that claims another page is available", async () => {
    const body = { intent: "alpha", results: [], expandedTerms: [],
      indexState: "READY", nextCursor: "more", facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    await expect(searchGrants("alpha", undefined, "cursor")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, nextCursor: null }), { status: 200 })));
    expect((await searchGrants("alpha")).results).toEqual([]);
  });

  it("rejects an empty index on continuation rather than treating old cards as current", async () => {
    const body = { intent: "alpha", results: [], expandedTerms: [],
      indexState: "EMPTY", nextCursor: null,
      facets: { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [], providersTruncated: false } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).indexState).toBe("EMPTY");
    await expect(searchGrants("alpha", undefined, "cursor")).rejects.toMatchObject({
      code: "INVALID_SEARCH_RESPONSE", status: 200,
    });
  });

  it("rejects a non-advancing continuation cursor but allows retry with an advancing page", async () => {
    const body = { intent: "alpha", results: [{ grantCallVersionId: "v1", grantCallId: "g1", title: "Test",
      summary: "Text", status: "OPEN", submissionCloseAt: null, providerName: "Obec",
      officialDetailUrl: null, capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" }], expandedTerms: [],
      indexState: "READY", nextCursor: "cursor", facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).nextCursor).toBe("cursor");
    await expect(searchGrants("alpha", undefined, "cursor")).rejects.toMatchObject({
      code: "INVALID_SEARCH_RESPONSE", status: 200,
    });
    expect((await searchGrants("alpha", undefined, "previous-cursor")).nextCursor).toBe("cursor");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...body, nextCursor: null }), { status: 200 })));
    expect((await searchGrants("alpha", undefined, "cursor")).nextCursor).toBeNull();
  });

  it("rejects a multi-page cursor cycle but permits retry with a new cursor", async () => {
    const result = { grantCallVersionId: "v3", grantCallId: "g3", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" };
    const body = { intent: "alpha", results: [result], expandedTerms: [],
      indexState: "READY", nextCursor: "cursor-a", facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    const seenCursors = new Set(["cursor-a", "cursor-b"]);
    await expect(searchGrants("alpha", undefined, "cursor-b", undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, new Set(["v1", "v2"]),
      new Set(["g1", "g2"]), seenCursors)).rejects.toMatchObject({
      code: "INVALID_SEARCH_RESPONSE", status: 200,
    });
    body.nextCursor = "cursor-c";
    expect((await searchGrants("alpha", undefined, "cursor-b", undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, new Set(["v1", "v2"]),
      new Set(["g1", "g2"]), seenCursors)).nextCursor).toBe("cursor-c");
    expect(seenCursors).toEqual(new Set(["cursor-a", "cursor-b"]));
  });

  it("accepts a complete response with source-specific result fields and facets", async () => {
    const body = { intent: "alpha", expandedTerms: ["sport"], indexState: "READY", nextCursor: "next",
      facets: { status: { OPEN: 1, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 1 }, providers: [{ name: "Obec", count: 1 }], providersTruncated: false },
      results: [{ grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
        status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
        capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" }] };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect(await searchGrants("alpha")).toEqual(body);
  });

  it("keeps the exact project cost on the initial and cursor requests", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "alpha", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("alpha", undefined, undefined, undefined, undefined, undefined,
      undefined, undefined, undefined, "GRANT", "300000");
    await searchGrants("alpha", undefined, "cursor", undefined, undefined, undefined,
      undefined, undefined, undefined, "GRANT", "300000");
    expect(urls).toEqual([
      "/api/search?intent=alpha&instrument=GRANT&projectBudgetCzk=300000",
      "/api/search?intent=alpha&cursor=cursor&instrument=GRANT&projectBudgetCzk=300000",
    ]);
  });
  it("preserves canonical instrument on first and continuation requests", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "alpha", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("alpha", undefined, undefined, undefined, undefined, undefined,
      undefined, undefined, undefined, "LOAN");
    await searchGrants("alpha", undefined, "next-page", undefined, undefined, undefined,
      undefined, undefined, undefined, "LOAN");
    expect(urls).toEqual([
      "/api/search?intent=alpha&instrument=LOAN",
      "/api/search?intent=alpha&cursor=next-page&instrument=LOAN",
    ]);
  });
  it("sends the actual intent to the API", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("intent=koupali%C5%A1t%C4%9B");
      return new Response(
        JSON.stringify({
          intent: "koupaliště",
          results: [],
          expandedTerms: ["Koupaliště", "Sportovní infrastruktura"],
          indexState: "READY",
          nextCursor: null,
          facets: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await searchGrants("koupaliště");
    expect(result.intent).toBe("koupaliště");
    expect(result.expandedTerms).toContain("Sportovní infrastruktura");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not silently replace an unavailable API with demo results", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ error: "SEARCH_UNAVAILABLE" }), {
          status: 503,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(searchGrants("koupaliště")).rejects.toMatchObject({
      code: "SEARCH_UNAVAILABLE",
      status: 503,
    });
  });

  it("sends a continuation cursor for the same intent", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("intent=koupali%C5%A1t%C4%9B&cursor=next-page");
      return new Response(JSON.stringify({ intent: "koupaliště", results: [],
        expandedTerms: [], indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    await searchGrants("koupaliště", undefined, "next-page");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("sends a fixed status on first and continuation requests, omitting the UI sentinel", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "strankovani", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("strankovani");
    await searchGrants("strankovani", undefined, undefined, "PLANNED");
    await searchGrants("strankovani", undefined, "next-page", "PLANNED");
    expect(urls).toEqual([
      "/api/search?intent=strankovani",
      "/api/search?intent=strankovani&status=PLANNED",
      "/api/search?intent=strankovani&cursor=next-page&status=PLANNED",
    ]);
  });

  it("sends a fixed deadline on first and continuation requests, omitting the UI sentinel", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "strankovani", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("strankovani");
    await searchGrants("strankovani", undefined, undefined, "PLANNED", "KNOWN");
    await searchGrants("strankovani", undefined, "next-page", "PLANNED", "KNOWN");
    expect(urls).toEqual([
      "/api/search?intent=strankovani",
      "/api/search?intent=strankovani&status=PLANNED&deadline=KNOWN",
      "/api/search?intent=strankovani&cursor=next-page&status=PLANNED&deadline=KNOWN",
    ]);
  });

  it("sends an exact provider on first and cursor requests", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "strankovani", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("strankovani", undefined, undefined, "PLANNED", "KNOWN", "E2E test provider B");
    await searchGrants("strankovani", undefined, "next-page", "PLANNED", "KNOWN", "E2E test provider B");
    expect(urls).toEqual([
      "/api/search?intent=strankovani&status=PLANNED&deadline=KNOWN&provider=E2E+test+provider+B",
      "/api/search?intent=strankovani&cursor=next-page&status=PLANNED&deadline=KNOWN&provider=E2E+test+provider+B",
    ]);
  });

  it("sends an inclusive cutoff on first and cursor requests", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "strankovani", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("strankovani", undefined, undefined, undefined, undefined, undefined, "2027-03-31");
    await searchGrants("strankovani", undefined, "next-page", undefined, undefined, undefined, "2027-03-31");
    expect(urls).toEqual([
      "/api/search?intent=strankovani&closesBy=2027-03-31",
      "/api/search?intent=strankovani&cursor=next-page&closesBy=2027-03-31",
    ]);
  });

  it("sends the inclusive start with the end and sort on first and cursor requests", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "strankovani", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("strankovani", undefined, undefined, undefined, undefined, undefined,
      "2027-05-31", "DEADLINE_LATEST", "2027-05-01");
    await searchGrants("strankovani", undefined, "next-page", undefined, undefined, undefined,
      "2027-05-31", "DEADLINE_LATEST", "2027-05-01");
    expect(urls).toEqual([
      "/api/search?intent=strankovani&closesBy=2027-05-31&closesFrom=2027-05-01&sort=DEADLINE_LATEST",
      "/api/search?intent=strankovani&cursor=next-page&closesBy=2027-05-31&closesFrom=2027-05-01&sort=DEADLINE_LATEST",
    ]);
  });

  it("sends date sort on first and continuation requests without changing default relevance", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return new Response(JSON.stringify({ intent: "strankovani", results: [], expandedTerms: [],
        indexState: "READY", nextCursor: null, facets: null }), { status: 200 });
    }));
    await searchGrants("strankovani", undefined, undefined, undefined, undefined, undefined, undefined, "RELEVANCE");
    await searchGrants("strankovani", undefined, undefined, undefined, undefined, undefined, undefined, "DEADLINE");
    await searchGrants("strankovani", undefined, "next-page", undefined, undefined, undefined, undefined, "DEADLINE");
    expect(urls).toEqual([
      "/api/search?intent=strankovani",
      "/api/search?intent=strankovani&sort=DEADLINE",
      "/api/search?intent=strankovani&cursor=next-page&sort=DEADLINE",
    ]);
  });

  it("explains local search backend unavailability", () => {
    expect(
      searchErrorMessage(
        Object.assign(new Error("SEARCH_UNAVAILABLE"), {
          code: "SEARCH_UNAVAILABLE",
          status: 503,
        }),
      ),
    ).toBe("Vyhledávání se teď nepodařilo dokončit.");
  });
});
