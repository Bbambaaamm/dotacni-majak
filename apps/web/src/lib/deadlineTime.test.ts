import { describe, expect, it } from "vitest";

import { conflictingDeadlineBounds, deadlineTime, sourceDeadlineNeedsReview } from "./deadlineTime";

describe("source deadline display", () => {
  it.each([
    ["2027-05-01", "2027-05-01"],
    ["2027-12-31T23:59:59Z", "2027-12-31 23:59:59 UTC"],
    ["2027-05-01T12:00:00z", "2027-05-01 12:00:00z"],
    ["2027-05-01T16:30:45.123+02:00", "2027-05-01 16:30:45.123+02:00"],
    ["2027-05-01T16:30-05:30", "2027-05-01 16:30-05:30"],
    ["2027-05-01T16:30:45", "2027-05-01T16:30:45"],
    ["TBD", "TBD"],
    ["not-a-date", "not-a-date"],
    [null, "Není uvedeno"],
  ])("formats %s as %s", (source, expected) => {
    expect(deadlineTime(source)).toBe(expected);
  });

  it.each([
    [null, false], ["2027-05-01", false], ["2027-05-01T16:30:45+02:00", false],
    ["2027-05-01T12:00:00z", false],
    ["2027-05-01T24:00:00Z", false], ["2027-02-30", true],
    ["2027-02-30T12:00:00Z", true], ["not-a-date", true],
    ["2027-05-01T16:30:45", true], ["", true],
  ])("flags unverified source deadline %s: %s", (source, expected) => {
    expect(sourceDeadlineNeedsReview(source)).toBe(expected);
  });

  it.each([
    ["2027-06-02", "2027-06-01", true],
    ["2027-06-01", "2027-06-01", false],
    ["2027-06-01T22:00:00+02:00", "2027-06-01T19:00:00Z", true],
    ["2027-06-01T22:00:00+02:00", "2027-06-01T20:00:00Z", false],
    ["2027-06-01", "2027-06-01T01:00:00Z", false],
    ["2027-06-01T01:00:00Z", "2027-05-31", false],
    ["2027-02-30", "2027-02-28", false],
    ["2027-06-01", "datum-nejasne", false],
    [null, "2027-06-01", false],
  ] as const)("flags only comparable reversed source bounds %s → %s: %s", (start, end, expected) => {
    expect(conflictingDeadlineBounds(start, end)).toBe(expected);
  });
});
