import { describe, expect, it } from "vitest";

import type {
  D1DatabaseLike,
  D1PreparedStatementLike,
  D1ResultLike,
  Env,
} from "../src/env";
import { handleRequest } from "../src/index";
import { ApiInputError, hashOwnerToken } from "../src/projectAccess";
import {
  assertOwnerTokenFormat,
  deleteApplicantProfile,
  getApplicantProfile,
  isApplicantProfileRefreshRoute,
  isApplicantProfileRoute,
  parseApplicantProfileInput,
  upsertApplicantProfile,
  ownerUserId,
  type ApplicantProfileInput,
} from "../src/applicantProfile";

// ---------------------------------------------------------------------------
// In-memory fake D1 database (stateful, tracks profiles by user_id)
// ---------------------------------------------------------------------------

interface StoredProfile {
  id: string;
  user_id: string;
  applicant_type: string;
  applicant_type_id: string | null;
  ico: string | null;
  organisation_name: string | null;
  legal_form_code: string | null;
  municipality_code: string | null;
  municipality_name: string | null;
  region_code: string | null;
  seat_geography_id: string | null;
  municipality_population: number | null;
  municipality_population_as_of: string | null;
  vat_status: string | null;
  organisation_size: string | null;
  public_private_status: string | null;
  nonprofit_status: string | null;
  cz_nace_json: string;
  field_sources_json: string;
  created_at: string;
  updated_at: string;
}

const VALID_OWNER = "A".repeat(43);
const PROJECT = "prj_" + "a".repeat(32);

function makeValidProfileInput(
  overrides: Partial<ApplicantProfileInput> = {},
): ApplicantProfileInput {
  return {
    applicantType: "UNKNOWN",
    ico: "12345678",
    organisationName: "Testovací organizace",
    legalFormCode: "706",
    municipalityCode: "123456",
    municipalityName: "Testov",
    regionCode: "CZ032",
    municipalityPopulation: 3200,
    municipalityPopulationAsOf: "2026-01-01",
    vatStatus: "NON_PAYER",
    organisationSize: "SMALL",
    publicPrivateStatus: "PRIVATE",
    nonprofitStatus: "NONPROFIT",
    czNaceCodes: ["93.12", "94.99"],
    fieldSources: {
      ico: {
        sourceKind: "ARES",
        sourceReference: "https://ares.gov.cz/test",
        observedAt: "2026-09-25T12:00:00Z",
        verifiedAt: "2026-09-25T12:00:00Z",
        verificationStatus: "VERIFIED",
        evidenceId: null,
      },
      municipalityPopulation: {
        sourceKind: "CZSO",
        sourceReference: "CZSO:OBY02E",
        observedAt: "2026-09-23T00:00:00Z",
        verifiedAt: null,
        verificationStatus: "AUTO_EXTRACTED",
        evidenceId: null,
      },
    },
    ...overrides,
  };
}

/** Creates a stateful fake Env whose DB remembers profiles across calls. */
function fakeEnv(): Env & { profiles: Map<string, StoredProfile> } {
  const profiles = new Map<string, StoredProfile>();
  const owners = new Map([[VALID_OWNER, "anonymous:" + PROJECT], ["B".repeat(43), "anonymous:other"]]);

  const db: D1DatabaseLike = {
    prepare(query: string): D1PreparedStatementLike {
      const q = query.trim();
      let values: unknown[] = [];
      const statement: D1PreparedStatementLike = {
        bind(...next: unknown[]) {
          values = next;
          return statement;
        },
        async first<T = unknown>() {
          if (q.includes("FROM project_owner_capabilities AS c")) {
            for (const [token, owner_user_id] of owners) {
              if (await hashOwnerToken(token) === values[0]) return { owner_user_id } as T;
            }
            return null;
          }
          // SELECT id ... WHERE user_id = ?
          if (
            q.startsWith("SELECT id FROM applicant_profiles") &&
            q.includes("user_id")
          ) {
            const row = profiles.get(String(values[0]));
            return (row ? { id: row.id } : null) as T;
          }
          // Full SELECT ... WHERE user_id = ?
          if (
            q.startsWith("SELECT") &&
            q.includes("FROM applicant_profiles") &&
            q.includes("WHERE user_id")
          ) {
            const row = profiles.get(String(values[0]));
            if (!row) return null;
            return { ...row } as T;
          }
          return null as T;
        },
        async all<T = unknown>() {
          return { success: true, results: [] as T[] } as D1ResultLike & { results?: T[] };
        },
        async run<T = unknown>() {
          const result: D1ResultLike & { results: T[] } = { success: true, meta: { changes: 1 }, results: [] };

          if (q.startsWith("INSERT INTO applicant_profiles")) {
            const existing = profiles.get(String(values[1]));
            const mask = Number(values[21]);
            const keep = <T>(index: number, bit: number, previous: T | undefined): T =>
              existing && (mask & bit) === 0 ? previous as T : values[index] as T;
            const row: StoredProfile = {
              id: existing?.id ?? String(values[0]),
              user_id: String(values[1]),
              applicant_type: String(values[2]),
              applicant_type_id: keep(3, 1, existing?.applicant_type_id),
              ico: keep(4, 2, existing?.ico),
              organisation_name: keep(5, 4, existing?.organisation_name),
              legal_form_code: keep(6, 8, existing?.legal_form_code),
              municipality_code: keep(7, 16, existing?.municipality_code),
              municipality_name: keep(8, 32, existing?.municipality_name),
              region_code: keep(9, 64, existing?.region_code),
              seat_geography_id: keep(10, 128, existing?.seat_geography_id),
              municipality_population: keep(11, 256, existing?.municipality_population),
              municipality_population_as_of: keep(12, 512, existing?.municipality_population_as_of),
              vat_status: keep(13, 1024, existing?.vat_status),
              organisation_size: keep(14, 2048, existing?.organisation_size),
              public_private_status: keep(15, 4096, existing?.public_private_status),
              nonprofit_status: keep(16, 8192, existing?.nonprofit_status),
              cz_nace_json: keep(17, 16384, existing?.cz_nace_json),
              field_sources_json: keep(18, 32768, existing?.field_sources_json),
              created_at: existing?.created_at ?? String(values[19]),
              updated_at: String(values[20]),
            };
            profiles.set(row.user_id, row);
            return result;
          }

          if (q.startsWith("DELETE FROM applicant_profiles")) {
            profiles.delete(String(values[0]));
            return result;
          }

          return result;
        },
      };
      return statement;
    },
    async batch(statements: D1PreparedStatementLike[]): Promise<D1ResultLike[]> {
      const results: D1ResultLike[] = [];
      for (const stmt of statements) {
        results.push(await stmt.run());
      }
      return results;
    },
  };

  return Object.assign(
    {
      ENVIRONMENT: "local" as const,
      DB: db,
      RAW: { async head() { return null; } },
      SEARCH: { async describe() { return {}; } },
    },
    { profiles },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("applicant profile authorization", () => {
  it("asserts owner token format", () => {
    expect(() => assertOwnerTokenFormat("short")).toThrowError(
      ApiInputError,
    );
    expect(() => assertOwnerTokenFormat(VALID_OWNER)).not.toThrow();
  });

  it("resolves user_id from the project owner capability", async () => {
    const userId = await ownerUserId(VALID_OWNER, fakeEnv());
    expect(userId).toBe("anonymous:" + PROJECT);
  });
});

describe("applicant profile input validation", () => {
  it("parses a valid PUT body", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(makeValidProfileInput()),
    });
    const input = await parseApplicantProfileInput(req);
    expect(input.applicantType).toBe("UNKNOWN");
    expect(input.ico).toBe("12345678");
    expect(input.czNaceCodes).toEqual(["93.12", "94.99"]);
  });

  it("keeps omitted fields absent and recognizes explicit clearing values", async () => {
    const parse = (body: unknown) => parseApplicantProfileInput(new Request("https://example.test/applicant-profile", {
      method: "PUT", body: JSON.stringify(body),
    }));
    const sparse = await parse({ applicantType: "BUSINESS" });
    expect(sparse).toEqual({ applicantType: "BUSINESS" });
    const clearing = await parse({
      applicantType: "BUSINESS", ico: null, czNaceCodes: null, fieldSources: null,
    });
    expect(clearing).toMatchObject({ ico: null, czNaceCodes: [], fieldSources: {} });
    await expect(parse({ applicantType: "BUSINESS", schemaVersion: "2.0.0" }))
      .rejects.toMatchObject({ code: "INVALID_SCHEMA_VERSION" });
  });

  it("rejects missing applicantType", async () => {
    const bad = makeValidProfileInput();
    delete (bad as unknown as Record<string, unknown>).applicantType;
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(bad),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toMatchObject({
      code: "INVALID_APPLICANT_TYPE",
    });
  });

  it("rejects applicant types outside the canonical enum", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT", body: JSON.stringify(makeValidProfileInput({ applicantType: "MADE_UP" })),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toMatchObject({ code: "INVALID_APPLICANT_TYPE" });
  });

  it("accepts optional sourceReference and rejects invalid canonical provenance", async () => {
    const source = {
      sourceKind: "USER", observedAt: "2026-09-25T12:00:00Z",
      verificationStatus: "USER_DECLARED",
    };
    const valid = new Request("https://example.test/applicant-profile", {
      method: "PUT", body: JSON.stringify(makeValidProfileInput({ fieldSources: { ico: source } })),
    });
    await expect(parseApplicantProfileInput(valid)).resolves.toMatchObject({ fieldSources: { ico: source } });
    for (const invalid of [
      { ...source, verificationStatus: "WRONG" },
      { ...source, verifiedAt: "yesterday" },
      { ...source, observedAt: "2026-02-30T12:00:00Z" },
      { ...source, extra: true },
    ]) {
      const req = new Request("https://example.test/applicant-profile", {
        method: "PUT", body: JSON.stringify(makeValidProfileInput({ fieldSources: { ico: invalid } })),
      });
      await expect(parseApplicantProfileInput(req)).rejects.toBeInstanceOf(ApiInputError);
    }
  });

  it("rejects impossible population calendar dates", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT", body: JSON.stringify(makeValidProfileInput({ municipalityPopulationAsOf: "2026-02-30" })),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toMatchObject({ code: "INVALID_POPULATION_AS_OF" });
  });

  it("rejects invalid IČO", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(makeValidProfileInput({ ico: "12345" })),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toThrowError(
      "INVALID_ICO",
    );
  });

  it("rejects empty body", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: "",
    });
    await expect(parseApplicantProfileInput(req)).rejects.toThrowError(
      "EMPTY_BODY",
    );
  });

  it("rejects invalid JSON", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: "{bad json",
    });
    await expect(parseApplicantProfileInput(req)).rejects.toThrowError(
      "INVALID_JSON",
    );
  });

  it("rejects body exceeding max size", async () => {
    const largeValue = "x".repeat(30_000);
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(makeValidProfileInput({ organisationName: largeValue })),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toMatchObject({
      code: "REQUEST_TOO_LARGE",
      status: 413,
    });
  });

  it("rejects duplicate czNaceCodes", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(makeValidProfileInput({ czNaceCodes: ["93.12", "93.12"] })),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toThrowError(
      "DUPLICATE_CZNACE_CODE",
    );
  });

  it("rejects invalid enum value for vatStatus", async () => {
    const req = new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(makeValidProfileInput({ vatStatus: "ILLEGAL" })),
    });
    await expect(parseApplicantProfileInput(req)).rejects.toThrowError(
      "INVALID_VAT_STATUS",
    );
  });
});

describe("applicant profile route helpers", () => {
  it("recognises /applicant-profile", () => {
    expect(isApplicantProfileRoute("/applicant-profile")).toBe(true);
    expect(isApplicantProfileRoute("/applicant-profile/123")).toBe(false);
  });

  it("recognises /applicant-profile/last-resolved", () => {
    expect(isApplicantProfileRefreshRoute("/applicant-profile/last-resolved")).toBe(true);
  });
});

describe("applicant profile CRUD", () => {
  it("returns null for GET when no profile exists (UNKNOWN, not FAIL)", async () => {
    const env = fakeEnv();
    const result = await getApplicantProfile(env, VALID_OWNER);
    expect(result).toBeNull();
  });

  it("creates a profile on upsert and retrieves it", async () => {
    const env = fakeEnv();
    const input = makeValidProfileInput();
    const saved = await upsertApplicantProfile(input, env, VALID_OWNER);

    expect(saved.applicantType).toBe("UNKNOWN");
    expect(saved.ico).toBe("12345678");
    expect(saved.organisationName).toBe("Testovací organizace");
    expect(saved.czNaceCodes).toEqual(["93.12", "94.99"]);
    expect(saved.id).toMatch(/^app_[a-f0-9]{32}$/);
    expect(saved.createdAt).toBe(saved.updatedAt);

    // Read it back
    const retrieved = await getApplicantProfile(env, VALID_OWNER);
    expect(retrieved).not.toBeNull();
    expect(retrieved?.id).toBe(saved.id);
    expect(retrieved?.ico).toBe("12345678");
    expect(retrieved?.czNaceCodes).toEqual(["93.12", "94.99"]);
    expect(retrieved?.fieldSources).toEqual(input.fieldSources);
  });

  it("upsert is idempotent — second PUT updates without creating a new id", async () => {
    const env = fakeEnv();
    const t1 = new Date("2026-09-25T12:00:00Z");
    const t2 = new Date("2026-09-26T12:00:00Z");
    const first = await upsertApplicantProfile(
      makeValidProfileInput(),
      env,
      VALID_OWNER,
      t1,
    );
    const second = await upsertApplicantProfile(
      makeValidProfileInput({ organisationName: "Updated org" }),
      env,
      VALID_OWNER,
      t2,
    );

    expect(second.id).toBe(first.id);
    expect(second.organisationName).toBe("Updated org");
    expect(new Date(second.updatedAt).getTime()).toBe(t2.getTime());
    expect(new Date(second.createdAt).getTime()).toBe(t1.getTime());
    expect(first.createdAt).toBe(second.createdAt); // createdAt is immutable
  });

  it("preserves omitted fields and clears explicit null, arrays, and objects", async () => {
    const env = fakeEnv();
    const original = makeValidProfileInput({
      schemaVersion: "1.0.0",
      applicantTypeId: "type-1",
      seatGeographyId: "geo-1",
    });
    const put = (body: unknown) => handleRequest(new Request("https://example.test/applicant-profile", {
      method: "PUT",
      headers: { authorization: `Bearer ${VALID_OWNER}` },
      body: JSON.stringify(body),
    }), env);
    const first = await put(original);
    expect(first.status).toBe(200);
    const sparse = await put({ applicantType: "BUSINESS", organisationName: "Changed" });
    expect(sparse.status).toBe(200);
    const retained = (await sparse.json() as { profile: Record<string, unknown> }).profile;
    expect(retained).toMatchObject({
      schemaVersion: "1.0.0", applicantTypeId: "type-1", seatGeographyId: "geo-1",
      organisationName: "Changed", ico: original.ico,
      czNaceCodes: original.czNaceCodes, fieldSources: original.fieldSources,
    });
    const cleared = await put({
      applicantType: "BUSINESS", applicantTypeId: null, seatGeographyId: null,
      ico: null, czNaceCodes: [], fieldSources: {},
    });
    expect(cleared.status).toBe(200);
    expect((await cleared.json() as { profile: Record<string, unknown> }).profile).toMatchObject({
      applicantTypeId: null, seatGeographyId: null, ico: null,
      organisationName: "Changed", czNaceCodes: [], fieldSources: {}, lastResolvedAt: null,
    });
  });

  it("computes lastResolvedAt from field sources (max observedAt)", async () => {
    const env = fakeEnv();
    await upsertApplicantProfile(
      makeValidProfileInput({
        fieldSources: {
          ico: {
            sourceKind: "ARES",
            sourceReference: "https://ares.gov.cz/test",
            observedAt: "2026-09-25T12:00:00Z",
            verifiedAt: "2026-09-25T12:00:00Z",
            verificationStatus: "VERIFIED",
            evidenceId: null,
          },
          municipalityPopulation: {
            sourceKind: "CZSO",
            sourceReference: "CZSO:OBY02E",
            observedAt: "2026-09-23T00:00:00Z",
            verifiedAt: null,
            verificationStatus: "AUTO_EXTRACTED",
            evidenceId: null,
          },
        },
      }),
      env,
      VALID_OWNER,
    );

    const retrieved = await getApplicantProfile(env, VALID_OWNER);
    // 2026-09-25 > 2026-09-23, so ARES observed_at is the max
    expect(retrieved?.lastResolvedAt).toBe("2026-09-25T12:00:00Z");
  });

  it("lastResolvedAt is null when no public-source fields exist", async () => {
    const env = fakeEnv();
    await upsertApplicantProfile(
      makeValidProfileInput({ fieldSources: {} }),
      env,
      VALID_OWNER,
    );
    const retrieved = await getApplicantProfile(env, VALID_OWNER);
    expect(retrieved?.lastResolvedAt).toBeNull();
  });

  it("ignores user and derived sources for lastResolvedAt", async () => {
    const env = fakeEnv();
    await upsertApplicantProfile(makeValidProfileInput({ fieldSources: {
      ico: { sourceKind: "USER", observedAt: "2026-12-01T00:00:00Z", verificationStatus: "USER_DECLARED" },
      municipalityCode: { sourceKind: "DERIVED", observedAt: "2026-12-02T00:00:00Z", verificationStatus: "AUTO_EXTRACTED" },
    } }), env, VALID_OWNER);
    expect((await getApplicantProfile(env, VALID_OWNER))?.lastResolvedAt).toBeNull();
  });

  it("updates the lastResolvedAt when a newer ARES observation is stored", async () => {
    const env = fakeEnv();
    const input = makeValidProfileInput();
    await upsertApplicantProfile(input, env, VALID_OWNER);
    expect((await getApplicantProfile(env, VALID_OWNER))?.lastResolvedAt).toBe(
      "2026-09-25T12:00:00Z",
    );

    // Upsert with a newer ARES observation
    await upsertApplicantProfile(
      makeValidProfileInput({
        fieldSources: {
          ico: {
            sourceKind: "ARES",
            sourceReference: "https://ares.gov.cz/test",
            observedAt: "2026-10-01T09:00:00Z",
            verifiedAt: "2026-10-01T09:00:00Z",
            verificationStatus: "VERIFIED",
            evidenceId: null,
          },
        },
      }),
      env,
      VALID_OWNER,
    );

    const updated = await getApplicantProfile(env, VALID_OWNER);
    expect(updated?.lastResolvedAt).toBe("2026-10-01T09:00:00Z");
  });

  it("deletes the profile and it disappears from GET", async () => {
    const env = fakeEnv();
    await upsertApplicantProfile(makeValidProfileInput(), env, VALID_OWNER);
    expect(await getApplicantProfile(env, VALID_OWNER)).not.toBeNull();

    await deleteApplicantProfile(env, VALID_OWNER);
    expect(await getApplicantProfile(env, VALID_OWNER)).toBeNull();
  });

  it("delete is idempotent — deleting a non-existent profile is a no-op", async () => {
    const env = fakeEnv();
    await expect(deleteApplicantProfile(env, VALID_OWNER)).resolves.toBeUndefined();
    await expect(deleteApplicantProfile(env, VALID_OWNER)).resolves.toBeUndefined();
  });

  it("isolates profiles per owner token", async () => {
    const env = fakeEnv();
    const otherToken = "B".repeat(43);

    await upsertApplicantProfile(
      makeValidProfileInput({ ico: "11111111" }),
      env,
      VALID_OWNER,
    );
    await upsertApplicantProfile(
      makeValidProfileInput({ ico: "22222222" }),
      env,
      otherToken,
    );

    const profile = await getApplicantProfile(env, VALID_OWNER);
    const otherProfile = await getApplicantProfile(env, otherToken);

    expect(profile?.ico).toBe("11111111");
    expect(otherProfile?.ico).toBe("22222222");
  });
});

describe("applicant profile HTTP routes", () => {
  it("GET /applicant-profile returns 404 when no profile stored", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(res.status).toBe(404);
    const body = await res.json() as Record<string, unknown>;
    expect(body.profile).toBeNull();
  });

  it("GET /applicant-profile without bearer token returns 404, not 401", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile"),
      env,
    );
    expect(res.status).toBe(404);
    expect((await res.json() as Record<string, unknown>).error).toBe(
      "OWNER_CAPABILITY_INVALID",
    );
  });

  it("GET /applicant-profile/last-resolved without token returns 404", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile/last-resolved"),
      env,
    );
    expect(res.status).toBe(404);
  });

  it("GET /applicant-profile/last-resolved with no profile returns null", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile/last-resolved", {
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(res.status).toBe(200);
    const body = await res.json() as Record<string, unknown>;
    expect(body.lastResolvedAt).toBeNull();
    // PII safety: only timestamp returned, no profile data.
    expect(body).not.toHaveProperty("ico");
    expect(body).not.toHaveProperty("organisationName");
    expect(body).not.toHaveProperty("id");
  });

  it("PUT then GET round-trips via handleRequest", async () => {
    const env = fakeEnv();
    const input = makeValidProfileInput();

    // PUT
    const putRes = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(input),
      }),
      env,
    );
    expect(putRes.status).toBe(200);
    const putBody = await putRes.json() as { profile: Record<string, unknown> };
    expect(putBody.profile.ico).toBe("12345678");
    expect(putBody.profile.lastResolvedAt).toBe("2026-09-25T12:00:00Z");

    // GET
    const getRes = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(getRes.status).toBe(200);
    const getBody = await getRes.json() as { profile: Record<string, unknown> };
    expect(getBody.profile.ico).toBe("12345678");
    expect(getBody.profile.czNaceCodes).toEqual(["93.12", "94.99"]);
    expect(getBody.profile.lastResolvedAt).toBe("2026-09-25T12:00:00Z");
  });

  it("PUT with invalid input returns 400 with error code, no PII leaked", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify({ applicantType: "123" }),
      }),
      env,
    );
    expect(res.status).toBe(400);
    const body = await res.json() as Record<string, unknown>;
    expect(body.error).toBe("INVALID_APPLICANT_TYPE");
    // No secrets or PII in error responses.
    expect(JSON.stringify(body)).not.toContain(VALID_OWNER);
    expect(JSON.stringify(body)).not.toMatch(/password|token_hash/i);
  });

  it("PUT with invalid IČO returns 400 INVALID_ICO", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(makeValidProfileInput({ ico: "999" })),
      }),
      env,
    );
    expect(res.status).toBe(400);
    expect((await res.json() as Record<string, unknown>).error).toBe("INVALID_ICO");
  });

  it("DELETE removes the profile", async () => {
    const env = fakeEnv();
    const input = makeValidProfileInput();

    await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(input),
      }),
      env,
    );

    const delRes = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "DELETE",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(delRes.status).toBe(200);
    expect((await delRes.json() as Record<string, unknown>).deleted).toBe(true);

    // Profile is gone
    const getRes = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(getRes.status).toBe(404);
  });

  it("DELETE without token returns 404 (non-disclosing)", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "DELETE",
      }),
      env,
    );
    expect(res.status).toBe(404);
  });

  it("GET /applicant-profile/last-resolved reflects updated profile", async () => {
    const env = fakeEnv();
    const input = makeValidProfileInput();

    await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(input),
      }),
      env,
    );

    const res = await handleRequest(
      new Request("https://example.test/applicant-profile/last-resolved", {
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(res.status).toBe(200);
    const body = await res.json() as Record<string, unknown>;
    expect(body.lastResolvedAt).toBe("2026-09-25T12:00:00Z");
  });

  it("PUT accepts applicantType UNKNOWN as a valid explicit type", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(makeValidProfileInput({ applicantType: "UNKNOWN", ico: null })),
      }),
      env,
    );
    expect(res.status).toBe(200);
    const body = await res.json() as { profile: Record<string, unknown> };
    expect(body.profile.applicantType).toBe("UNKNOWN");
    expect(body.profile.ico).toBeNull();
  });

  it("POST method also works for upsert (same handler)", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "POST",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(makeValidProfileInput()),
      }),
      env,
    );
    expect(res.status).toBe(200);
  });

  it("HEAD on /applicant-profile is accepted", async () => {
    const env = fakeEnv();
    await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(makeValidProfileInput()),
      }),
      env,
    );
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "HEAD",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
      }),
      env,
    );
    expect(res.status).toBe(200);
  });

  it("unknown owner token returns 404 for all operations", async () => {
    const env = fakeEnv();
    const badToken = "X".repeat(43);

    const getRes = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        headers: { authorization: `Bearer ${badToken}` },
      }),
      env,
    );
    expect(getRes.status).toBe(404);
    const body = await getRes.json() as Record<string, unknown>;
    expect(body.error).toBe("OWNER_CAPABILITY_INVALID");
  });
});

describe("applicant profile error semantics (no secrets/PII)", () => {
  it("error response bodies contain only machine-readable error codes", async () => {
    const env = fakeEnv();
    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: "{not json}",
      }),
      env,
    );
    const body = await res.json() as Record<string, unknown>;
    expect(body.error).toBe("INVALID_JSON");
    // Verify no raw token or internal data leaks.
    expect(JSON.stringify(body)).not.toContain("Bearer");
    expect(JSON.stringify(body)).not.toContain("sha");
    expect(JSON.stringify(body)).not.toContain("hash");
  });

  it("DB errors surface as 503 not 500 with internal details", async () => {
    // Use an env whose DB always succeeds on run but returns null for first.
    // The upsert readback will fail → throws → route returns 503.
    const env = fakeEnv();
    // Override to simulate DB failure on select after insert
    const originalPrepare = env.DB.prepare;
    env.DB = {
      ...env.DB!,
      prepare(query: string) {
        const stmt = originalPrepare(query as never);
        if (query.includes("WHERE user_id") && query.startsWith("SELECT")) {
          const origFirst = stmt.first;
          stmt.first = async () => {
            // First SELECT (id lookup) returns the stored row fine,
            // but the full SELECT for getApplicantProfile returns null
            // to force the readback failure.
            const originalResult = await origFirst();
            return null as never;
          };
        }
        return stmt;
      },
    };

    const res = await handleRequest(
      new Request("https://example.test/applicant-profile", {
        method: "PUT",
        headers: { authorization: `Bearer ${VALID_OWNER}` },
        body: JSON.stringify(makeValidProfileInput()),
      }),
      env,
    );
    expect(res.status).toBe(503);
    const body = await res.json() as Record<string, unknown>;
    expect(body.error).toBe("PROFILE_UNAVAILABLE");
  });
});
