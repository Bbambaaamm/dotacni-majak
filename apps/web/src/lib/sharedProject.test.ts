import { describe, expect, it, vi } from "vitest";

import {
  apiUrl,
  formatMinorMoney,
  loadSharedProject,
  sharedProjectTokenFromPath,
} from "./sharedProject";

const TOKEN = "A".repeat(43);

describe("shared project client", () => {
  it("extracts only valid share capability routes", () => {
    expect(sharedProjectTokenFromPath(`/s/${TOKEN}`)).toBe(TOKEN);
    expect(sharedProjectTokenFromPath("/s/tiny")).toBeNull();
    expect(sharedProjectTokenFromPath(`/s/${TOKEN}/extra`)).toBeNull();
  });

  it("rejects insecure remote API base URL", () => {
    expect(() => apiUrl("/share/x", "http://example.com")).toThrow();
    expect(apiUrl("/share/x", "http://localhost:8787")).toContain("localhost");
  });

  it("maps unknown/revoked share to not-found", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ error: "SHARE_NOT_FOUND" }), { status: 404 }),
    );
    await expect(loadSharedProject(TOKEN, fetcher, "https://api.example.com"))
      .resolves.toEqual({ status: "not-found" });
  });

  it("accepts only the safe project projection", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        project: {
          id: "prj_" + "a".repeat(32),
          title: "Kurty",
          intent: "Rekonstrukce tenisových kurtů",
          currencyCode: "CZK",
          estimatedTotalBudgetMinor: 400000000,
          plannedStart: "2027-01-01",
          plannedEnd: null,
          updatedAt: "2026-09-23T20:00:00.000Z",
        },
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    const result = await loadSharedProject(TOKEN, fetcher, "https://api.example.com");
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.project).not.toHaveProperty("owner_user_id");
      expect(result.project.intent).toContain("tenisových");
    }
  });

  it("formats integer minor units", () => {
    expect(formatMinorMoney(400000000, "CZK")).toContain("4");
  });
});
