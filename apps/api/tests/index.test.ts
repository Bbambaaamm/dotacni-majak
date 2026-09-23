import { describe, expect, it } from "vitest";

import type { D1PreparedStatementLike, Env } from "../src/env";
import { handleRequest } from "../src/index";
import { hashShareToken } from "../src/share";

type DbResolver = (query: string, values: unknown[]) => unknown;

function env(
  dbResult: unknown = { ok: 1 },
  resolver?: DbResolver,
): Env {
  return {
    ENVIRONMENT: "local",
    DB: {
      prepare(query: string): D1PreparedStatementLike {
        let values: unknown[] = [];
        const statement: D1PreparedStatementLike = {
          bind(...next: unknown[]) {
            values = next;
            return statement;
          },
          async first<T = unknown>() {
            const value = resolver ? resolver(query, values) : dbResult;
            return value as T | null;
          },
        };
        return statement;
      },
    },
    RAW: {
      async head() {
        return null;
      },
    },
    SEARCH: {
      async describe() {
        return {};
      },
    },
  };
}

describe("api worker", () => {
  it("reports health without touching remote services", async () => {
    const response = await handleRequest(
      new Request("https://example.test/health"),
      env(),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      status: "ok",
      service: "dotacni-majak-api",
      environment: "local",
    });
  });

  it("reports ready only when D1 check succeeds", async () => {
    const ok = await handleRequest(new Request("https://example.test/ready"), env());
    expect(ok.status).toBe(200);

    const failed = await handleRequest(
      new Request("https://example.test/ready"),
      env(null),
    );
    expect(failed.status).toBe(503);
  });

  it("rejects state-changing HTTP methods by default", async () => {
    const response = await handleRequest(
      new Request("https://example.test/health", { method: "POST" }),
      env(),
    );
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("GET, HEAD");
  });

  it("returns only whitelisted fields from a valid read-only share", async () => {
    const token = "A".repeat(43);
    const expectedHash = await hashShareToken(token);
    const response = await handleRequest(
      new Request(`https://example.test/share/${token}`),
      env(null, (query, values) => {
        expect(query).toContain("project_share_links");
        expect(values[0]).toBe(expectedHash);
        expect(typeof values[1]).toBe("string");
        return {
          id: "p1",
          title: "Tenisové kurty",
          natural_language_intent: "Rekonstrukce tenisových kurtů",
          currency_code: "CZK",
          estimated_total_budget_minor: 400_000_000,
          planned_start: "2027-01-01",
          planned_end: "2027-12-31",
          updated_at: "2026-09-23T20:00:00Z",
          owner_user_id: "must-never-leak",
          applicant_profile_id: "must-never-leak",
        };
      }),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("x-robots-tag")).toBe("noindex, nofollow");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    const body = await response.json() as Record<string, unknown>;
    expect(body).toEqual({
      project: {
        id: "p1",
        title: "Tenisové kurty",
        intent: "Rekonstrukce tenisových kurtů",
        currencyCode: "CZK",
        estimatedTotalBudgetMinor: 400_000_000,
        plannedStart: "2027-01-01",
        plannedEnd: "2027-12-31",
        updatedAt: "2026-09-23T20:00:00Z",
      },
    });
    expect(JSON.stringify(body)).not.toContain("must-never-leak");
  });

  it("collapses malformed, revoked, expired and unknown shares to 404", async () => {
    const malformed = await handleRequest(
      new Request("https://example.test/share/tiny"),
      env(null, () => {
        throw new Error("DB should not be touched for malformed token");
      }),
    );
    expect(malformed.status).toBe(404);

    const unknown = await handleRequest(
      new Request(`https://example.test/share/${"B".repeat(43)}`),
      env(null, () => null),
    );
    expect(unknown.status).toBe(404);
    expect(await unknown.json()).toEqual({ error: "SHARE_NOT_FOUND" });
    expect(unknown.headers.get("x-robots-tag")).toBe("noindex, nofollow");
  });
});
