import { describe, expect, it } from "vitest";

import { sourceCalendarDate } from "./sourceCalendarDate";

describe("source calendar date display", () => {
  it.each([
    ["2026-10-02T00:30:00+14:00", "2. října 2026"],
    ["2026-10-01T23:30:00-10:00", "1. října 2026"],
    ["2026-10-02T00:30:00Z", "2. října 2026"],
    ["2026-10-02", "2. října 2026"],
    ["2026-02-30", "2026-02-30"],
    ["not-a-date", "not-a-date"],
    [null, "Není uvedeno"],
  ])("preserves the source day of %s", (source, expected) => {
    expect(sourceCalendarDate(source)).toBe(expected);
  });
});