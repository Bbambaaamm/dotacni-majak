import { describe, expect, it } from "vitest";

import { toPublicSourceCoverage } from "./sourceCoverage";

describe("public source coverage", () => {
  it("healthy source does not claim last-known-good fallback", () => {
    const item = toPublicSourceCoverage({
      code: "NSA",
      name: "Národní sportovní agentura",
      category: "ČR",
      status: "HEALTHY",
      lastCheckedLabel: "před 5 minutami",
      lastSuccessLabel: "před 5 minutami",
    });
    expect(item.statusLabel).toBe("Aktivní");
    expect(item.servesLastKnownGood).toBe(false);
  });

  it("degraded source explicitly serves last-known-good data", () => {
    const item = toPublicSourceCoverage({
      code: "X",
      name: "Zdroj X",
      category: "ČR",
      status: "DEGRADED",
      lastCheckedLabel: "dnes 10:00",
      lastSuccessLabel: "včera 03:00",
      limitation: "Změnil se HTML listing.",
    });
    expect(item.statusLabel).toBe("Omezené");
    expect(item.servesLastKnownGood).toBe(true);
    expect(item.limitation).toContain("HTML");
  });

  it("never-success state does not invent a success time", () => {
    const item = toPublicSourceCoverage({
      code: "NEW",
      name: "Nový zdroj",
      category: "ČR",
      status: "UNAVAILABLE",
      lastCheckedLabel: "dnes",
      lastSuccessLabel: null,
    });
    expect(item.lastSuccessLabel).toContain("bez úspěšné");
  });
});
