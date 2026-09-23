import { describe, expect, it } from "vitest";

import {
  parseDemoResultState,
  resultStateContent,
} from "./resultState";

describe("result state UX", () => {
  it("no-results always offers project watch instead of a dead end", () => {
    const state = resultStateContent("NO_RESULTS");
    expect(state.primaryLabel).toBe("Pohlídat tento záměr");
    expect(state.primaryHref).not.toBe("");
  });

  it("ineligible explains a concrete blocking condition", () => {
    const state = resultStateContent("INELIGIBLE");
    expect(state.details.join(" ")).toContain("pouze obcím");
    expect(state.primaryLabel).toContain("podobné");
  });

  it("unknown explicitly asks for information instead of turning into fail", () => {
    const state = resultStateContent("UNKNOWN");
    expect(state.title).toContain("informaci");
    expect(state.description).toContain(
      "nepovažujeme automaticky za splněný ani nesplněný",
    );
  });

  it("source unavailable communicates last-known-good semantics", () => {
    const state = resultStateContent("SOURCE_UNAVAILABLE");
    expect(state.title).toContain("poslední ověřená data");
    expect(state.sourceLastSuccess).toBeTruthy();
    expect(state.primaryHref).toBe("/pokryti");
  });

  it("demo query parsing is closed over known states", () => {
    expect(parseDemoResultState("unknown")).toBe("UNKNOWN");
    expect(parseDemoResultState("anything-else")).toBeNull();
  });
});
