import { describe, expect, it } from "vitest";

import { normalizePath, resolveRoute } from "./routes";

describe("route foundation", () => {
  it("normalizes duplicate and trailing slashes", () => {
    expect(normalizePath("//projekty///")).toBe("/projekty");
  });

  it("resolves known route", () => {
    expect(resolveRoute("/hledat").id).toBe("search");
  });

  it("does not silently redirect unknown route to home", () => {
    expect(resolveRoute("/neexistuje").id).toBe("not-found");
  });
});
