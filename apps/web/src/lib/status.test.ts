import { describe, expect, it } from "vitest";

import { statusPresentation } from "./status";

describe("status presentation", () => {
  it("always exposes a textual label in addition to visual styling", () => {
    for (const kind of ["success", "warning", "error", "info", "unknown"] as const) {
      const presentation = statusPresentation(kind);
      expect(presentation.label.length).toBeGreaterThan(0);
      expect(presentation.symbol.length).toBeGreaterThan(0);
    }
  });

  it("uses explicit unknown wording instead of fail", () => {
    expect(statusPresentation("unknown").label).toBe("Potřebujeme doplnit");
  });
});
