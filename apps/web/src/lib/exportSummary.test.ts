import { describe, expect, it } from "vitest";

import {
  demoExportSummary,
  validateExportSummary,
} from "./exportSummary";

describe("auditable export summary", () => {
  it("accepts the documented fixture", () => {
    expect(validateExportSummary(demoExportSummary)).toBe(demoExportSummary);
  });

  it("rejects export without provenance", () => {
    expect(() =>
      validateExportSummary({
        ...demoExportSummary,
        evidence: [],
      }),
    ).toThrow(/provenance/);
  });

  it("rejects non-HTTPS provenance", () => {
    expect(() =>
      validateExportSummary({
        ...demoExportSummary,
        evidence: [
          {
            label: "Unsafe",
            url: "http://example.com",
            checkedAt: "2026-09-23",
          },
        ],
      }),
    ).toThrow(/HTTPS/);
  });
});
