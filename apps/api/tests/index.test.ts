import { describe, expect, it } from "vitest";

import type {
  D1PreparedStatementLike,
  D1ResultLike,
  Env,
} from "../src/env";
import { handleRequest } from "../src/index";
import { hashOwnerToken } from "../src/projectAccess";
import { hashShareToken } from "../src/share";

type DbResolver = (
  query: string,
  values: unknown[],
  mode: "first" | "all" | "run",
) => unknown;

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
            const value = resolver ? resolver(query, values, "first") : dbResult;
            return value as T | null;
          },
          async all<T = unknown>() {
            const value = resolver ? resolver(query, values, "all") : null;
            if (value && typeof value === "object" && "results" in (value as object)) {
              return value as D1ResultLike & { results?: T[] };
            }
            return { success: true, results: (Array.isArray(value) ? value : []) as T[] };
          },
          async run<T = unknown>() {
            const value = resolver ? resolver(query, values, "run") : null;
            if (value && typeof value === "object" && "success" in (value as object)) {
              return value as D1ResultLike & { results?: T[] };
            }
            return { success: true, meta: { changes: 1 }, results: [] as T[] };
          },
        };
        return statement;
      },
      async batch(statements: D1PreparedStatementLike[]) {
        const results: D1ResultLike[] = [];
        for (const statement of statements) {
          results.push(await statement.run());
        }
        return results;
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

  it("searches the D1 FTS index with the actual intent", async () => {
    const response = await handleRequest(
      new Request("https://example.test/search?intent=koupali%C5%A1t%C4%9B"),
      env(null, (query, values, mode) => {
        if (mode === "all" && query.includes("grant_search_fts")) {
          expect(values[0]).toContain("koupaliště");
          return {
            success: true,
            results: [
              {
                grant_call_version_id: "v-swim",
                grant_call_id: "g-swim",
                title: "Modernizace sportovní infrastruktury",
                summary: "Podpora sportovních zařízení.",
                status: "OPEN",
                submission_close_at: "2026-12-31T23:59:59Z",
                provider_name: "Testovací poskytovatel",
                official_detail_url: "https://example.test/grant",
                rank: -2.5,
              },
            ],
          };
        }
        return null;
      }),
    );
    expect(response.status).toBe(200);
    const body = await response.json() as {
      intent: string;
      results: Array<{ title: string; matchKind: string }>;
      expandedTerms: string[];
    };
    expect(body.intent).toBe("koupaliště");
    expect(body.results[0]?.title).toBe("Modernizace sportovní infrastruktury");
    expect(body.results[0]?.matchKind).toBe("DIRECT");
    expect(body.expandedTerms).toContain("Sportovní infrastruktura");
  });

  it("creates project and owner capability through a three-statement atomic batch", async () => {
    const queries: string[] = [];
    const response = await handleRequest(
      new Request("https://example.test/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          title: "Tenisové kurty",
          naturalLanguageIntent: "Chceme zrekonstruovat tenisové kurty",
          currencyCode: "CZK",
          estimatedTotalBudgetMinor: 400_000_000,
        }),
      }),
      env(null, (query) => {
        queries.push(query);
        return { success: true, meta: { changes: 1 } };
      }),
    );
    expect(response.status).toBe(201);
    const body = await response.json() as {
      projectId: string;
      ownerCapability: string;
    };
    expect(body.projectId).toMatch(/^prj_[a-f0-9]{32}$/);
    expect(body.ownerCapability).toMatch(/^[A-Za-z0-9_-]{40,128}$/);
    expect(queries).toHaveLength(3);
    expect(queries[0]).toContain("INSERT INTO projects");
    expect(queries[1]).toContain("project_owner_capabilities");
    expect(queries[2]).toContain("project_owner_audit_events");
  });

  it("creates a read-only share only with matching owner capability", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "B".repeat(43);
    const expectedOwnerHash = await hashOwnerToken(owner);
    let insertValues: unknown[] = [];

    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/shares`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${owner}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ expiresInDays: 7 }),
      }),
      env(null, (query, values, mode) => {
        if (query.includes("INSERT INTO project_share_links")) {
          insertValues = values;
          expect(mode).toBe("run");
          return { success: true, meta: { changes: 1 } };
        }
        return { success: true, meta: { changes: 1 } };
      }),
    );

    expect(response.status).toBe(201);
    const body = await response.json() as {
      shareId: string;
      token: string;
      sharePath: string;
    };
    expect(body.shareId).toMatch(/^shr_[a-f0-9]{32}$/);
    expect(body.token).toMatch(/^[A-Za-z0-9_-]{40,128}$/);
    expect(body.sharePath).toBe(`/s/${body.token}`);
    expect(insertValues.at(-1)).toBe(expectedOwnerHash);
    expect(insertValues).not.toContain(owner);
  });

  it("returns 404 when share create owner capability cannot authorize project", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/shares`, {
        method: "POST",
        headers: { authorization: `Bearer ${"B".repeat(43)}` },
      }),
      env(null, (query) => ({
        success: true,
        meta: { changes: query.includes("project_share_links") ? 0 : 0 },
      })),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "OWNER_CAPABILITY_INVALID" });
  });

  it("share revocation is idempotent and non-disclosing", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const shareId = "shr_" + "c".repeat(32);
    const response = await handleRequest(
      new Request(
        `https://example.test/projects/${projectId}/shares/${shareId}`,
        {
          method: "DELETE",
          headers: { authorization: `Bearer ${"D".repeat(43)}` },
        },
      ),
      env(null, () => ({ success: true, meta: { changes: 0 } })),
    );
    expect(response.status).toBe(204);
  });

  it("rotates owner capability and does not return the old token", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "E".repeat(43);
    const expectedOldHash = await hashOwnerToken(owner);
    let updateValues: unknown[] = [];
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/owner/rotate`, {
        method: "POST",
        headers: { authorization: `Bearer ${owner}` },
      }),
      env(null, (query, values) => {
        if (query.includes("UPDATE project_owner_capabilities")) {
          updateValues = values;
        }
        return { success: true, meta: { changes: 1 } };
      }),
    );
    expect(response.status).toBe(200);
    const body = await response.json() as { ownerCapability: string };
    expect(body.ownerCapability).not.toBe(owner);
    expect(updateValues).toContain(expectedOldHash);
    expect(updateValues).not.toContain(owner);
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
    expect(JSON.stringify(body)).not.toContain("must-never-leak");
  });

  it("collapses malformed and unknown shares to 404", async () => {
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
  });

  it("rejects unsupported methods", async () => {
    const response = await handleRequest(
      new Request("https://example.test/health", { method: "PATCH" }),
      env(),
    );
    expect(response.status).toBe(405);
  });
});
