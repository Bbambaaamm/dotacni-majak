import { describe, expect, it } from "vitest";
import type { GrantSourceRef } from "./grantDetailApi";
import { allSourcesMissing, mixedSourcePresence, sourcePresenceLabel } from "./sourcePresence";

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

  it("identifies all-missing records without treating a seen source as missing", () => {
    expect(allSourcesMissing(sources("MISSING_CANDIDATE"))).toBe(true);
    expect(allSourcesMissing(sources("CONFIRMED_MISSING", "MISSING_CANDIDATE"))).toBe(true);
    expect(allSourcesMissing(sources("CONFIRMED_MISSING", "SEEN"))).toBe(false);
    expect(allSourcesMissing(sources("MISSING_CANDIDATE", "OTHER"))).toBe(false);
    expect(allSourcesMissing(sources())).toBe(false);
  });

  it("identifies mixed seen and missing records without treating unknown or empty records as mixed", () => {
    expect(mixedSourcePresence(sources("MISSING_CANDIDATE", "SEEN"))).toBe(true);
    expect(mixedSourcePresence(sources("SEEN", "CONFIRMED_MISSING"))).toBe(true);
    expect(mixedSourcePresence(sources("SEEN", "OTHER"))).toBe(false);
    expect(mixedSourcePresence(sources("MISSING_CANDIDATE", "OTHER"))).toBe(false);
    expect(mixedSourcePresence(sources("SEEN"))).toBe(false);
    expect(mixedSourcePresence(sources())).toBe(false);
  });
});
