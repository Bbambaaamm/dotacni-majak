import { describe, expect, it } from "vitest";

import type {
  D1DatabaseLike,
  D1PreparedStatementLike,
  D1ResultLike,
} from "../src/env";
import {
  getGrantDetail,
  grantCallIdFromPath,
} from "../src/grantDetail";

type Resolver = (
  query: string,
  values: unknown[],
  mode: "first" | "all" | "run",
) => unknown;

function db(resolver: Resolver): D1DatabaseLike {
  return {
    prepare(query: string): D1PreparedStatementLike {
      let values: unknown[] = [];
      const statement: D1PreparedStatementLike = {
        bind(...next: unknown[]) {
          values = next;
          return statement;
        },
        async first<T = unknown>() {
          return resolver(query, values, "first") as T | null;
        },
        async all<T = unknown>() {
          const value = resolver(query, values, "all");
          if (value && typeof value === "object" && "results" in (value as object)) {
            return value as D1ResultLike & { results?: T[] };
          }
          return {
            success: true,
            results: (Array.isArray(value) ? value : []) as T[],
          };
        },
        async run<T = unknown>() {
          const value = resolver(query, values, "run");
          return (
            value && typeof value === "object" && "success" in (value as object)
              ? value
              : { success: true, results: [] }
          ) as D1ResultLike & { results?: T[] };
        },
      };
      return statement;
    },
    async batch(statements: D1PreparedStatementLike[]) {
      return Promise.all(statements.map((statement) => statement.run()));
    },
  };
}

describe("grant detail query", () => {
  it("parses URL encoded grant ids safely", () => {
    expect(grantCallIdFromPath("/grants/grant%3Ansa%3A16-2026")).toBe(
      "grant:nsa:16-2026",
    );
    expect(grantCallIdFromPath("/grants/")).toBeNull();
    expect(grantCallIdFromPath("/grants/%E0%A4%A")).toBeNull();
  });

  it("returns current canonical detail with source fallback provenance", async () => {
    const detail = await getGrantDetail(
      db((query, values, mode) => {
        if (mode === "first" && query.includes("FROM grant_calls g")) {
          expect(values).toEqual(["grant:nsa:16-2026"]);
          return {
            grant_call_id: "grant:nsa:16-2026",
            canonical_code: "16/2026",
            canonical_slug: "nsa-16-2026",
            version_id: "version:nsa:16-2026:v1",
            version_number: 1,
            captured_at: "2026-09-24T00:00:00Z",
            title: "Regiony 2026",
            summary: "Technické zhodnocení sportovní infrastruktury.",
            status: "OPEN",
            verification_status: "PARTIALLY_VERIFIED",
            published_at: "2026-01-01T00:00:00Z",
            submission_open_at: "2026-01-15T00:00:00Z",
            submission_close_at: "2026-10-31T23:59:59Z",
            application_url: null,
            official_detail_url: "https://nsa.gov.cz/dotace/regiony-2026/",
            currency_code: "CZK",
            programme_id: "programme:nsa:investment",
            programme_name: "NSA — Investiční výzvy",
            funding_origin: "CZ_NATIONAL",
            programme_official_url: "https://nsa.gov.cz/",
            provider_id: "provider:nsa",
            provider_name: "Národní sportovní agentura",
            provider_type: "NATIONAL",
            provider_official_url: "https://nsa.gov.cz/",
          };
        }
        if (mode === "all" && query.includes("FROM source_records sr")) {
          return [{
            source_code: "NSA",
            source_name: "Národní sportovní agentura",
            canonical_url: "https://nsa.gov.cz/dotace/regiony-2026/",
            last_seen_at: "2026-09-24T00:00:00Z",
            presence_state: "SEEN",
          }];
        }
        if (mode === "all" && query.includes("FROM grant_deadlines")) return [];
        if (mode === "all" && query.includes("FROM funding_scenarios")) return [];
        if (mode === "all" && query.includes("FROM grant_requirements")) return [];
        if (mode === "all" && query.includes("FROM field_evidence")) return [];
        if (mode === "all" && query.includes("FROM change_events")) return [];
        if (mode === "all" && query.includes("FROM grant_call_versions")) {
          return [{
            id: "version:nsa:16-2026:v1",
            version_number: 1,
            captured_at: "2026-09-24T00:00:00Z",
            status: "OPEN",
            verification_status: "PARTIALLY_VERIFIED",
            submission_close_at: "2026-10-31T23:59:59Z",
          }];
        }
        return [];
      }),
      "grant:nsa:16-2026",
    );

    expect(detail).not.toBeNull();
    expect(detail?.provider.name).toBe("Národní sportovní agentura");
    expect(detail?.deadlines).toEqual([
      expect.objectContaining({
        type: "APPLICATION_WINDOW",
        startsAt: "2026-01-15T00:00:00Z",
        endsAt: "2026-10-31T23:59:59Z",
      }),
    ]);
    expect(detail?.availability).toEqual({
      funding: "UNKNOWN",
      requirements: "UNKNOWN",
      evidence: "SOURCE_ONLY",
    });
    expect(detail?.sources[0]?.canonicalUrl).toContain("nsa.gov.cz");
  });

  it("returns null for an unknown grant", async () => {
    const detail = await getGrantDetail(
      db((_query, _values, mode) => (mode === "first" ? null : [])),
      "missing",
    );
    expect(detail).toBeNull();
  });
});
