import { describe, expect, it } from "vitest";

import { buildIntentSearchUrl, readIntentFromSearch } from "./intent";

describe("intent search URLs", () => {
  it("normalizes whitespace and URL-encodes the intent", () => {
    const url = buildIntentSearchUrl("  rekonstrukce   tenisových kurtů  ");
    expect(url).toBe(
      "/hledat?intent=rekonstrukce+tenisov%C3%BDch+kurt%C5%AF",
    );
  });

  it("reads the actual search intent instead of a demo value", () => {
    expect(readIntentFromSearch("?intent=koupali%C5%A1t%C4%9B")).toBe("koupaliště");
  });

  it("does not create an empty query parameter", () => {
    expect(buildIntentSearchUrl("   ")).toBe("/hledat");
  });
});
