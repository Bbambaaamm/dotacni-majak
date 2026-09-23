import { describe, expect, it } from "vitest";

import { normalizePath, resolveRoute } from "./routes";

describe("route foundation", () => {
  it("normalizes duplicate and trailing slashes", () => {
    expect(normalizePath("//projekty///")).toBe("/projekty");
  });

  it("resolves known route", () => {
    expect(resolveRoute("/hledat").id).toBe("search");
  });

  it("resolves grant detail route", () => {
    expect(resolveRoute("/dotace/regiony-2026").id).toBe("grant-detail");
  });

  it("resolves public changelog route", () => {
    expect(resolveRoute("/changelog").id).toBe("changelog");
  });

  it("resolves export route", () => {
    expect(resolveRoute("/export/regiony-2026").id).toBe("export-summary");
  });

  it("does not silently redirect unknown route to home", () => {
    expect(resolveRoute("/neexistuje").id).toBe("not-found");
  });
});
