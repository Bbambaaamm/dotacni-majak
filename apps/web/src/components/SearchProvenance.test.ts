import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SearchProvenance } from "./SearchProvenance";

describe("search result provenance", () => {
  it("labels captured version metadata and cautions against inferring live acceptance", () => {
    const html = renderToStaticMarkup(createElement(SearchProvenance, { capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED" }));
    expect(html).toContain("Verze zachycena</dt><dd>26. září 2026");
    expect(html).toContain("Ověření zachycené verze</dt><dd>Ověřeno");
    expect(html).toContain('role="note"');
    expect(html).toContain("nepotvrzují aktuální podmínky nebo příjem žádostí");
  });
});
