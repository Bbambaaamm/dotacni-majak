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
