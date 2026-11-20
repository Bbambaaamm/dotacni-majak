import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { OfficialSourceLink } from "./OfficialSourceLink";

describe("OfficialSourceLink", () => {
  it("keeps source label and safe link for an HTTP document", () => {
    const html = renderToStaticMarkup(createElement(OfficialSourceLink, {
      url: "https://nsa.gov.cz/dokument.pdf", children: "Doklad podmínky",
    }));
    expect(html).toContain('href="https://nsa.gov.cz/dokument.pdf"');
    expect(html).toContain("Doklad podmínky");
  });

  it("keeps evidence legible but does not render an unsafe link", () => {
    const html = renderToStaticMarkup(createElement(OfficialSourceLink, {
      url: "javascript:alert(1)", children: "Doklad podmínky",
    }));
    expect(html).not.toContain("<a");
    expect(html).toContain("Doklad podmínky");
    expect(html).toContain("odkaz není bezpečně dostupný");
  });
});
