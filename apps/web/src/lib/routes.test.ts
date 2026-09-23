import { describe, expect, it } from "vitest";

import { normalizePath, resolveRoute } from "./routes";

describe("route foundation", () => {
  it("normalizes duplicate and trailing slashes", () => {
    expect(normalizePath("//projekty///")).toBe("/projekty");
  });

  it("resolves known route", () => {
    expect(resolveRoute("/hledat").id).toBe("search");
  });

  it("resolves grant detail route", () => {\n    expect(resolveRoute("/dotace/regiony-2026").id).toBe("grant-detail");\n  });\n\n  it("does not silently redirect unknown route to home", () => {
    expect(resolveRoute("/neexistuje").id).toBe("not-found");
  });
});
