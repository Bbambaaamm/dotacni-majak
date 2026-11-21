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
      matchKind: "DIRECT" };
    const valid = { intent: "alpha", expandedTerms: [], indexState: "READY", nextCursor: null,
      facets: null, results: [result] };
    for (const body of [
      { ...valid, indexState: "EMPTY" },
      { ...valid, indexState: "EMPTY", results: [], nextCursor: "more" },
      ...[
        { grantCallVersionId: "" }, { grantCallId: "" }, { title: "  " },
        { providerName: "  " }, { status: "CANCELLED" }, { status: "UNVERIFIED" },
      ].map((change) => ({ ...valid, results: [{ ...result, ...change }] })),
    ]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
      await expect(searchGrants("alpha")).rejects.toMatchObject({ code: "INVALID_SEARCH_RESPONSE", status: 200 });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...valid,
      indexState: "EMPTY", results: [], nextCursor: null }), { status: 200 })));
    expect((await searchGrants("alpha")).indexState).toBe("EMPTY");
  });

  it("rejects facet counts that contradict visible results, without treating unavailable counts as zero", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      matchKind: "DIRECT" };
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

  it("rejects positive facet counts for an empty index rather than claiming it contains no calls", async () => {
    const zero = { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [], providersTruncated: false };
    const body = { intent: "alpha", results: [], expandedTerms: [],
      indexState: "EMPTY", nextCursor: null, facets: zero };
    for (const facets of [
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
    const facets = { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [{ name: "Obec", count: 2 }],
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
      ...body, facets: { ...facets, providers: [] },
    }), { status: 200 })));
    expect((await searchGrants("alpha")).facets?.providers).toEqual([]);
  });

  it("rejects repeated version identities within and across pages without advancing pagination", async () => {
    const result = { grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
      status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
      matchKind: "DIRECT" };
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
      matchKind: "DIRECT" };
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
      indexState: "EMPTY", nextCursor: null, facets: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await searchGrants("alpha")).indexState).toBe("EMPTY");
    await expect(searchGrants("alpha", undefined, "cursor")).rejects.toMatchObject({
      code: "INVALID_SEARCH_RESPONSE", status: 200,
    });
  });

  it("rejects a non-advancing continuation cursor but allows retry with an advancing page", async () => {
    const body = { intent: "alpha", results: [{ grantCallVersionId: "v1", grantCallId: "g1", title: "Test",
      summary: "Text", status: "OPEN", submissionCloseAt: null, providerName: "Obec",
      officialDetailUrl: null, matchKind: "DIRECT" }], expandedTerms: [],
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

  it("accepts a complete response with source-specific result fields and facets", async () => {
    const body = { intent: "alpha", expandedTerms: ["sport"], indexState: "READY", nextCursor: "next",
      facets: { status: { OPEN: 1, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 1 }, providers: [{ name: "Obec", count: 1 }], providersTruncated: false },
      results: [{ grantCallVersionId: "v1", grantCallId: "g1", title: "Test", summary: "Text",
        status: "OPEN", submissionCloseAt: null, providerName: "Obec", officialDetailUrl: null,
        matchKind: "DIRECT" }] };
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
