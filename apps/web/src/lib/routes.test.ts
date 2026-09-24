import { describe, expect, it } from "vitest";

import { grantCallIdFromWebPath, normalizePath, resolveRoute } from "./routes";

describe("route foundation", () => {
  it("normalizes duplicate and trailing slashes", () => {
    expect(normalizePath("//projekty///")).toBe("/projekty");
  });

  it("resolves known route", () => {
    expect(resolveRoute("/hledat").id).toBe("search");
  });

  it("resolves dynamic grant detail route and decodes canonical id", () => {
    const path = "/dotace/grant%3Ansa%3A16-2026";
    expect(resolveRoute(path).id).toBe("grant-detail");
    expect(grantCallIdFromWebPath(path)).toBe("grant:nsa:16-2026");
    expect(grantCallIdFromWebPath("/dotace/%E0%A4%A")).toBeNull();
  });

  it("resolves public changelog route", () => {
    expect(resolveRoute("/changelog").id).toBe("changelog");
  });

  it("resolves export route", () => {
    expect(resolveRoute("/export/regiony-2026").id).toBe("export-summary");
  });

  it("resolves only well-shaped read-only share routes", () => {
    expect(resolveRoute("/s/" + "A".repeat(43)).id).toBe("shared-project");
    expect(resolveRoute("/s/tiny").id).toBe("not-found");
  });

  it("does not silently redirect unknown route to home", () => {
    expect(resolveRoute("/neexistuje").id).toBe("not-found");
  });
});
