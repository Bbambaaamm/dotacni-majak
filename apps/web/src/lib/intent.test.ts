import { describe, expect, it } from "vitest";

import { buildIntentSearchUrl } from "./intent";

describe("intent search URLs", () => {
  it("normalizes whitespace and URL-encodes the intent", () => {
    const url = buildIntentSearchUrl("  rekonstrukce   tenisových kurtů  ");
    expect(url).toBe(
      "/hledat?intent=rekonstrukce+tenisov%C3%BDch+kurt%C5%AF",
    );
  });

  it("does not create an empty query parameter", () => {
    expect(buildIntentSearchUrl("   ")).toBe("/hledat");
  });
});
