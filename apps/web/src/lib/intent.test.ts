import { describe, expect, it } from "vitest";

import { buildDetailSearchQuery, buildIntentSearchUrl, buildSearchUrl, readIntentFromSearch, readSearchUrlState } from "./intent";

describe("intent search URLs", () => {
  it("normalizes whitespace and URL-encodes the intent", () => {
    const url = buildIntentSearchUrl("  rekonstrukce   tenisových kurtů  ");
    expect(url).toBe(
      "/hledat?intent=rekonstrukce+tenisov%C3%BDch+kurt%C5%AF",
    );
  });

  it("reads the actual search intent instead of a demo value", () => {
    expect(readIntentFromSearch("?intent=koupali%C5%A1t%C4%9B")).toBe("koupaliště");
  });

  it("does not create an empty query parameter", () => {
    expect(buildIntentSearchUrl("   ")).toBe("/hledat");
  });
});

describe("search return state", () => {
  it("round trips every API filter and sort through the detail query", () => {
    const state = readSearchUrlState("?intent=digitalizace%20obce&status=OPEN&instrument=GRANT&projectBudgetCzk=300000&provider=E2E+test+provider+A&deadline=KNOWN&closesFrom=2026-01-01&closesBy=2026-12-31&sort=DEADLINE_LATEST");
    const detailQuery = buildDetailSearchQuery(state);
    expect(readSearchUrlState(`?${detailQuery}`)).toEqual(state);
    expect(buildSearchUrl(state)).toContain("projectBudgetCzk=300000");
    expect(buildSearchUrl(state)).toContain("sort=DEADLINE_LATEST");
  });

  it("drops duplicate and malformed fields and never accepts a redirect or cursor", () => {
    const state = readSearchUrlState("?intent=test&status=OPEN&status=PLANNED&provider=%20bad&closesBy=2026-02-30&sort=INVALID&return=https%3A%2F%2Fevil.invalid&cursor=abc");
    expect(buildSearchUrl(state)).toBe("/hledat?intent=test");
    expect(buildSearchUrl(readSearchUrlState("?intent=one&intent=two"))).toBe("/hledat");
    expect(buildSearchUrl(readSearchUrlState(`?intent=test&provider=${"x".repeat(201)}`))).toBe("/hledat?intent=test");
    expect(buildSearchUrl(readSearchUrlState(`?intent=${"x".repeat(501)}`))).toBe("/hledat");
  });

  it("keeps an invalid combination out of the first request", () => {
    const state = readSearchUrlState("?intent=test&deadline=UNKNOWN&closesFrom=2026-01-01&projectBudgetCzk=300000&instrument=LOAN");
    expect(state).toMatchObject({ deadline: "UNKNOWN", closesFrom: "", instrument: "GRANT" });
  });
});
