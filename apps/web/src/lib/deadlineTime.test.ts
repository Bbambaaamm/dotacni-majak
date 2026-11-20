import { describe, expect, it } from "vitest";

import { deadlineTime } from "./deadlineTime";

describe("source deadline display", () => {
  it.each([
    ["2027-05-01", "2027-05-01"],
    ["2027-12-31T23:59:59Z", "2027-12-31 23:59:59 UTC"],
    ["2027-05-01T16:30:45.123+02:00", "2027-05-01 16:30:45.123+02:00"],
    ["2027-05-01T16:30-05:30", "2027-05-01 16:30-05:30"],
    ["2027-05-01T16:30:45", "2027-05-01T16:30:45"],
    ["TBD", "TBD"],
    ["not-a-date", "not-a-date"],
    [null, "Není uvedeno"],
  ])("formats %s as %s", (source, expected) => {
    expect(deadlineTime(source)).toBe(expected);
  });
});
