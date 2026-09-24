import { describe, expect, it } from "vitest";

import { projectPrefillFromSearch } from "./projectPrefill";

describe("project prefill", () => {
  it("preserves intent and explicit watch opt-in", () => {
    expect(
      projectPrefillFromSearch(
        "?intent=Rekonstrukce%20tenisov%C3%BDch%20kurt%C5%AF&watch=1",
      ),
    ).toEqual({
      intent: "Rekonstrukce tenisových kurtů",
      autoWatch: true,
    });
  });

  it("does not opt in to watch implicitly", () => {
    expect(projectPrefillFromSearch("?intent=Koupali%C5%A1t%C4%9B")).toEqual({
      intent: "Koupaliště",
      autoWatch: false,
    });
  });

  it("normalizes whitespace and caps untrusted URL input", () => {
    const value = "  a   b  " + "x".repeat(5000);
    const result = projectPrefillFromSearch(
      "?intent=" + encodeURIComponent(value) + "&watch=1",
    );
    expect(result.intent.startsWith("a b ")).toBe(true);
    expect(result.intent.length).toBe(4000);
    expect(result.autoWatch).toBe(true);
  });
});
