import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SourceDeadline } from "./GrantDetailPage";

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
