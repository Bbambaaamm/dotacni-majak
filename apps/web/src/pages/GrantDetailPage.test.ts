import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SourceDeadline, SourceObservation } from "./GrantDetailPage";

describe("detail source deadline", () => {
  it.each([
    [null, false],
    ["2027-06-01", false],
    ["2027-06-01T12:30:00z", false],
    ["datum-nejasne", true],
    ["2027-02-30T12:30:00Z", true],
    ["2027-06-01T12:30:00", true],
  ])("keeps %s and marks caution %s", (value, caution) => {
    const html = renderToStaticMarkup(createElement(SourceDeadline, { value }));
    expect(html).toContain(value ? value.slice(0, 10) : "Není uvedeno");
    expect(html.includes('role="note"')).toBe(caution);
    if (caution) expect(html).toContain("ověřte jej v oficiálním zdroji");
  });
});

describe("detail source observation", () => {
  const source = {
    sourceCode: "official", sourceName: "Zdroj", canonicalUrl: "https://example.org",
    lastSeenAt: "2026-10-01T23:30:00-10:00", presenceState: "SEEN",
  };

  it("selects the latest instant but does not silently ignore an unverified source date", () => {
    const html = renderToStaticMarkup(createElement(SourceObservation, { sources: [
      source,
      { ...source, sourceCode: "other", lastSeenAt: "2026-10-02T00:30:00+14:00" },
      { ...source, sourceCode: "malformed", lastSeenAt: "2026-02-30T12:00:00Z" },
    ] }));
    expect(html).toContain("1. října 2026");
    expect(html).toContain('role="note"');
    expect(html).toContain("nemusí být nejnovější");
  });

  it("does not promote an unparseable observation to a confirmed recency", () => {
    const html = renderToStaticMarkup(createElement(SourceObservation, { sources: [
      { ...source, lastSeenAt: "datum-nejasne" },
    ] }));
    expect(html).toContain("Není doložena");
    expect(html).toContain('role="note"');
    expect(renderToStaticMarkup(createElement(SourceObservation, { sources: [] }))).toBe("Není doložena");
    expect(renderToStaticMarkup(createElement(SourceObservation, { sources: [source] })))
      .not.toContain('role="note"');
  });
});
