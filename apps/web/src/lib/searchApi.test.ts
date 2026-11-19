import { afterEach, describe, expect, it, vi } from "vitest";

import { searchErrorMessage, searchGrants } from "./searchApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("search API client", () => {
  it("sends the actual intent to the API", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("intent=koupali%C5%A1t%C4%9B");
      return new Response(
        JSON.stringify({
          intent: "koupaliště",
          results: [],
          expandedTerms: ["Koupaliště", "Sportovní infrastruktura"],
          indexState: "READY",
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
        expandedTerms: [], indexState: "READY", nextCursor: null }), { status: 200 });
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
        indexState: "READY", nextCursor: null }), { status: 200 });
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
        indexState: "READY", nextCursor: null }), { status: 200 });
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
        indexState: "READY", nextCursor: null }), { status: 200 });
    }));
    await searchGrants("strankovani", undefined, undefined, "PLANNED", "KNOWN", "E2E test provider B");
    await searchGrants("strankovani", undefined, "next-page", "PLANNED", "KNOWN", "E2E test provider B");
    expect(urls).toEqual([
      "/api/search?intent=strankovani&status=PLANNED&deadline=KNOWN&provider=E2E+test+provider+B",
      "/api/search?intent=strankovani&cursor=next-page&status=PLANNED&deadline=KNOWN&provider=E2E+test+provider+B",
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
