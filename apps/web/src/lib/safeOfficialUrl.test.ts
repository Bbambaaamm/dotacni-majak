import { describe, expect, it } from "vitest";

import { safeOfficialUrl } from "./safeOfficialUrl";

describe("safeOfficialUrl", () => {
  it("preserves absolute HTTP(S) source URLs", () => {
    expect(safeOfficialUrl("https://nsa.gov.cz/vyzva?x=1#detail")).toBe("https://nsa.gov.cz/vyzva?x=1#detail");
    expect(safeOfficialUrl("http://example.invalid/document.pdf")).toBe("http://example.invalid/document.pdf");
  });

  it.each([null, "", "//example.invalid/path", "/dotace", "javascript:alert(1)",
    "data:text/html,test", "file:///etc/passwd", "https://user:password@example.invalid/",
    " https://example.invalid/", "https://example.invalid/\n", "https://", "https://example.invalid\u0000/"])(
    "rejects untrusted source URL %s", (value) => {
      expect(safeOfficialUrl(value)).toBeNull();
    },
  );
});
