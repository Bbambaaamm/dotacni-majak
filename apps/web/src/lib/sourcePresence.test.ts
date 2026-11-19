import { describe, expect, it } from "vitest";
import type { GrantSourceRef } from "./grantDetailApi";
import { allSourcesMissing, sourcePresenceLabel } from "./sourcePresence";

const sources = (...states: string[]): GrantSourceRef[] => states.map((presenceState) => ({
  sourceCode: presenceState,
  sourceName: presenceState,
  canonicalUrl: "https://example.invalid",
  lastSeenAt: "2026-09-26T20:00:00Z",
  presenceState,
}));

describe("source presence presentation", () => {
  it("keeps candidate provisional and confirmed missing scoped to the source", () => {
    expect(sourcePresenceLabel("SEEN")).toBe("Viděn u zdroje");
    expect(sourcePresenceLabel("MISSING_CANDIDATE")).toContain("předběžné");
    expect(sourcePresenceLabel("CONFIRMED_MISSING")).toContain("neznamená zrušení výzvy");
    expect(sourcePresenceLabel("OTHER")).toBe("Výskyt u zdroje není známý");
  });

  it("warns only when all known records are missing or candidates", () => {
    expect(allSourcesMissing(sources("MISSING_CANDIDATE"))).toBe(true);
    expect(allSourcesMissing(sources("CONFIRMED_MISSING", "MISSING_CANDIDATE"))).toBe(true);
    expect(allSourcesMissing(sources("CONFIRMED_MISSING", "SEEN"))).toBe(false);
    expect(allSourcesMissing(sources("MISSING_CANDIDATE", "OTHER"))).toBe(false);
    expect(allSourcesMissing(sources())).toBe(false);
  });
});
