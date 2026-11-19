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
    ATTACHMENTS: {
      async put(_key, options) {
        return { key: options?.body ? String(options.body) : "" };
      },
      async delete(_key) {
        return true;
      },
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
        if (mode === "first" && query.includes("COUNT(*) AS count")) {
          return { count: 1 };
        }
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

  it("returns current dynamic grant detail from D1", async () => {
    const response = await handleRequest(
      new Request("https://example.test/grants/grant%3Ansa%3A16-2026"),
      env(null, (query, values, mode) => {
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
            summary: "Sportovní infrastruktura",
            status: "OPEN",
            verification_status: "PARTIALLY_VERIFIED",
            published_at: null,
            submission_open_at: null,
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
        if (mode === "all") return [];
        return null;
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toContain("max-age=60");
    const body = await response.json() as {
      grantCallId: string;
      title: string;
      provider: { name: string };
      availability: { funding: string };
    };
    expect(body.grantCallId).toBe("grant:nsa:16-2026");
    expect(body.title).toBe("Regiony 2026");
    expect(body.provider.name).toBe("Národní sportovní agentura");
    expect(body.availability.funding).toBe("UNKNOWN");
  });

  it("returns 404 for unknown dynamic grant detail", async () => {
    const response = await handleRequest(
      new Request("https://example.test/grants/missing"),
      env(null, (_query, _values, mode) => mode === "first" ? null : []),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "GRANT_NOT_FOUND" });
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

  it("creates an owner-protected project watch through the API", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "W".repeat(43);
    const watchId = "wch_" + "b".repeat(32);

    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/watch`, {
        method: "POST",
        headers: { authorization: `Bearer ${owner}` },
      }),
      env(null, (query, _values, mode) => {
        if (
          mode === "first"
          && query.includes("FROM project_owner_capabilities")
        ) {
          return { ok: 1 };
        }
        if (mode === "first" && query.includes("FROM watches")) {
          return {
            id: watchId,
            project_id: projectId,
            enabled: 1,
            minimum_match_band: "POSSIBLE",
            created_at: "2026-09-24T00:00:00Z",
            updated_at: "2026-09-24T00:00:00Z",
          };
        }
        if (mode === "run") {
          return { success: true, meta: { changes: 1 } };
        }
        return null;
      }),
    );

    expect(response.status).toBe(200);
    const body = await response.json() as {
      watch: { id: string; projectId: string; enabled: boolean };
    };
    expect(body.watch).toMatchObject({
      id: watchId,
      projectId,
      enabled: true,
    });
  });

  it("does not disclose project watch without owner capability", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/watch`),
      env(null, () => {
        throw new Error("DB must not be touched without bearer capability");
      }),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({
      error: "OWNER_CAPABILITY_INVALID",
    });
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

  it("creates a user document attachment for an authorized project owner", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const expectedOwnerHash = await hashOwnerToken(owner);
    const payload = new Uint8Array(512).buffer;
    let ownerLookup = false;
    let insertValues: unknown[] = [];

    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${owner}`,
          "content-type": "application/pdf",
          "x-attachment-filename": "vypocty.pdf",
          "content-length": String(payload.byteLength),
        },
        body: payload,
      }),
      env(null, (query, values, mode) => {
        if (query.includes("FROM project_owner_capabilities") && mode === "first") {
          ownerLookup = true;
          return { ok: 1 };
        }
        if (query.includes("INNER JOIN project_owner_capabilities") && mode === "first") {
          return { owner_user_id: `anonymous:${projectId}` };
        }
        if (query.includes("INSERT INTO user_document_attachments") && mode === "run") {
          insertValues = values;
          return { success: true, meta: { changes: 1 } };
        }
        if (query.includes("INSERT INTO user_document_attachment_events") && mode === "run") {
          return { success: true, meta: { changes: 1 } };
        }
        // Official source-document tables must never be touched by the
        // user-attachment flow (AC3: official vs user separation).
        if (
          query.includes("source_documents") ||
          query.includes("document_versions") ||
          query.includes("field_evidence")
        ) {
          throw new Error("ATTACHMENT_FLOW_TOUCHED_OFFICIAL_TABLE");
        }
        return { success: true, meta: { changes: 1 } };
      }),
    );

    expect(response.status).toBe(201);
    expect(ownerLookup).toBe(true);
    const body = await response.json() as {
      attachment: {
        id: string;
        projectId: string;
        filename: string;
        mimeType: string;
        sizeBytes: number;
        status: string;
        createdAt: string;
        updatedAt: string;
      };
    };
    expect(body.attachment.id).toMatch(/^att_[a-f0-9]{32}$/);
    expect(body.attachment.projectId).toBe(projectId);
    expect(body.attachment.filename).toBe("vypocty.pdf");
    expect(body.attachment.mimeType).toBe("application/pdf");
    expect(body.attachment.sizeBytes).toBe(512);
    expect(body.attachment.status).toBe("UPLOADED");
    expect(body.attachment.createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    // owner_user_id (the principal) is stored, not the raw token or hash.
    expect(insertValues).toContain(`anonymous:${projectId}`);
    expect(insertValues).not.toContain(owner);
  });

  it("rejects attachment creation without an owner capability", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          "content-type": "application/pdf",
          "x-attachment-filename": "vypocty.pdf",
        },
        body: new Uint8Array(10).buffer,
      }),
      env(),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "OWNER_CAPABILITY_INVALID" });
  });

  it("rejects attachment creation for a non-owner caller", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${"x".repeat(43)}`,
          "content-type": "application/pdf",
          "x-attachment-filename": "vypocty.pdf",
        },
        body: new Uint8Array(10).buffer,
      }),
      env(null, (query) => {
        if (query.includes("FROM project_owner_capabilities")) {
          return { ok: 0 };
        }
        return { success: true, meta: { changes: 1 } };
      }),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "OWNER_CAPABILITY_INVALID" });
  });

  it("returns 404 for an unknown attachment id", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments/att_${"b".repeat(32)}`, {
        method: "GET",
        headers: { authorization: `Bearer ${owner}` },
      }),
      env(null, (query, _values, mode) => {
        if (query.includes("FROM project_owner_capabilities") && mode === "first") {
          return { ok: 1 };
        }
        if (mode === "first") {
          return null;
        }
        return { success: true, results: [] };
      }),
    );
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "ATTACHMENT_NOT_FOUND" });
  });

  it("lists attachments for an authorized project owner", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "GET",
        headers: { authorization: `Bearer ${owner}` },
      }),
      env(null, (query, _values, mode) => {
        if (query.includes("FROM project_owner_capabilities") && mode === "first") {
          return { ok: 1 };
        }
        if (query.includes("user_document_attachments") && mode === "all") {
          return {
            success: true,
            results: [
              {
                id: "att_" + "c".repeat(32),
                project_id: projectId,
                filename: "plan.xlsx",
                mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size_bytes: 8192,
                status: "UPLOADED",
                created_at: "2026-10-01T10:00:00Z",
                updated_at: "2026-10-01T10:00:00Z",
              },
            ],
          };
        }
        return { success: true, results: [] };
      }),
    );
    expect(response.status).toBe(200);
    const body = await response.json() as { attachments: unknown[] };
    expect(body.attachments).toHaveLength(1);
    expect(body.attachments[0]).toMatchObject({
      id: "att_" + "c".repeat(32),
      filename: "plan.xlsx",
    });
  });

  it("deletes an attachment for an authorized project owner", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const attachmentId = "att_" + "d".repeat(32);
    let updateQuery = "";
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments/${attachmentId}`, {
        method: "DELETE",
        headers: { authorization: `Bearer ${owner}` },
      }),
      env(null, (query, _values, mode) => {
        if (query.includes("FROM project_owner_capabilities") && mode === "first") {
          return { ok: 1 };
        }
        if (query.includes("SELECT storage_key") && mode === "first") {
          return { storage_key: "proj/" + projectId + "/" + attachmentId + "/key" };
        }
        if (query.includes("UPDATE user_document_attachments") && mode === "run") {
          updateQuery = query;
          return { success: true, meta: { changes: 1 } };
        }
        if (mode === "run") {
          return { success: true, meta: { changes: 1 } };
        }
        return { success: true, results: [] };
      }),
    );
    expect(response.status).toBe(204);
    expect(updateQuery).toContain("SET status = 'DELETED'");
  });

  it("rejects disallowed attachment MIME types", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${owner}`,
          "content-type": "application/x-executable",
          "x-attachment-filename": "malware.exe",
        },
        body: new Uint8Array(10).buffer,
      }),
      env(),
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "INVALID_ATTACHMENT_MIME" });
  });

  it("rejects attachment filenames with path traversal", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${owner}`,
          "content-type": "application/pdf",
          "x-attachment-filename": "../etc/passwd",
        },
        body: new Uint8Array(10).buffer,
      }),
      env(),
    );
    expect(response.status).toBe(400);
  });

  it("rejects attachment payloads exceeding the size limit", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const large = new Uint8Array(11 * 1024 * 1024);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${owner}`,
          "content-type": "application/pdf",
          "x-attachment-filename": "big.pdf",
          "content-length": String(large.byteLength),
        },
        body: large,
      }),
      env(),
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "ATTACHMENT_TOO_LARGE" });
  });

  it("rejects empty attachment payloads", async () => {
    const projectId = "prj_" + "a".repeat(32);
    const owner = "O".repeat(43);
    const response = await handleRequest(
      new Request(`https://example.test/projects/${projectId}/attachments`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${owner}`,
          "content-type": "application/pdf",
          "x-attachment-filename": "empty.pdf",
        },
        body: new Uint8Array(0).buffer,
      }),
      env(),
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "INVALID_ATTACHMENT_EMPTY" });
  });
});
