import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGrantDetail } from "./grantDetailApi";

const detail = {
  grantCallId: "grant:one", canonicalCode: null, canonicalSlug: "grant-one",
  versionId: "v1", versionNumber: 1, capturedAt: "2026-01-01T00:00:00Z",
  title: "Výzva", summary: "Popis", status: "OPEN", verificationStatus: "VERIFIED",
  publishedAt: null, submissionOpenAt: null, submissionCloseAt: null,
  applicationUrl: null, officialDetailUrl: null, currencyCode: null,
  fundingInstrumentType: "GRANT",
  provider: { id: "provider", name: "Poskytovatel", type: "PUBLIC", officialUrl: null },
  programme: { id: "programme", name: "Program", fundingOrigin: "NATIONAL", officialUrl: null },
  sources: [{ sourceCode: "source", sourceName: "Zdroj", canonicalUrl: "https://example.org",
    lastSeenAt: "2026-01-01T00:00:00Z", presenceState: "SEEN" }],
  deadlines: [{ id: "d1", type: "APPLICATION_CLOSE", startsAt: null, endsAt: null,
    timezone: null, description: null, evidenceId: null }],
  fundingScenarios: [{ id: "f1", name: "Scénář", conditionGroupId: null,
    instrumentType: "GRANT", currencyCode: "CZK", supportRateMinBps: null,
    supportRateMaxBps: 9000, grantAmountMinMinor: null, grantAmountMaxMinor: null,
    projectCostMinMinor: null, projectCostMaxMinor: null, paymentMode: null,
    vatRule: null, advancePaymentAllowed: null, evidenceId: null }],
  requirements: [{ id: "r1", type: "DOCUMENT", title: "Doklad", description: null,
    necessity: "REQUIRED", phase: null, evidenceId: null }],
  evidence: [{ id: "e1", fieldPath: "status", pageFrom: null, pageTo: null,
    evidenceText: null, verificationStatus: "VERIFIED", documentTitle: null,
    sourceUrl: "https://example.org", retrievedAt: "2026-01-01T00:00:00Z" }],
  changes: [{ id: "c1", changeType: "STATUS", severity: "INFO", fieldPath: null,
    oldValue: null, newValue: "OPEN", createdAt: "2026-01-01T00:00:00Z" }],
  versions: [{ id: "v1", versionNumber: 1, capturedAt: "2026-01-01T00:00:00Z",
    status: "OPEN", verificationStatus: "VERIFIED", submissionCloseAt: null,
    isCurrent: true }],
  availability: { funding: "AVAILABLE", requirements: "AVAILABLE", evidence: "AVAILABLE" },
};

function respond(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("grant detail API boundary", () => {
  it("accepts complete detail with unknown values and preserves the requested identity", async () => {
    respond(detail);
    expect(await fetchGrantDetail("grant:one")).toEqual(detail);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/grants/grant%3Aone", expect.any(Object));
    respond({ ...detail, availability: { funding: "UNKNOWN", requirements: "UNKNOWN", evidence: "SOURCE_ONLY" },
      fundingScenarios: [], requirements: [], evidence: [] });
    expect((await fetchGrantDetail("grant:one")).availability.funding).toBe("UNKNOWN");
  });

  it("rejects malformed success instead of showing false provenance, finance or eligibility", async () => {
    const invalid = [null, [], { ...detail, grantCallId: "another" },
      { ...detail, sources: undefined }, { ...detail, sources: [{}] },
      { ...detail, provider: null }, { ...detail, availability: undefined },
      { ...detail, availability: { funding: "AVAILABLE", requirements: "FAIL", evidence: "AVAILABLE" } },
      { ...detail, fundingScenarios: [{ ...detail.fundingScenarios[0], supportRateMaxBps: "90%" }] },
      { ...detail, requirements: [{ ...detail.requirements[0], evidenceId: undefined }] },
      { ...detail, changes: [{ ...detail.changes[0], oldValue: undefined }] },
      { ...detail, versions: [{ ...detail.versions[0], isCurrent: "true" }] }];
    for (const body of invalid) {
      respond(body);
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not-json", { status: 200 })));
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({ code: "INVALID_GRANT_DETAIL_RESPONSE" });
  });

  it("rejects impossible finance bounds instead of displaying misleading amounts or rates", async () => {
    const scenario = detail.fundingScenarios[0];
    const invalid = [
      { supportRateMinBps: -1 }, { supportRateMaxBps: 10001 },
      { supportRateMaxBps: 1.5 }, { supportRateMinBps: 9001 },
      { grantAmountMinMinor: -1 }, { grantAmountMaxMinor: 1.5 },
      { grantAmountMaxMinor: Number.MAX_SAFE_INTEGER + 1 },
      { grantAmountMinMinor: 200, grantAmountMaxMinor: 100 },
      { projectCostMinMinor: -1 }, { projectCostMaxMinor: 1.5 },
      { projectCostMinMinor: 200, projectCostMaxMinor: 100 },
    ];
    for (const change of invalid) {
      respond({ ...detail, fundingScenarios: [{ ...scenario, ...change }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    respond({ ...detail, fundingScenarios: [{ ...scenario,
      supportRateMinBps: 0, supportRateMaxBps: 10000,
      grantAmountMinMinor: 0, grantAmountMaxMinor: Number.MAX_SAFE_INTEGER,
      projectCostMinMinor: 0, projectCostMaxMinor: Number.MAX_SAFE_INTEGER,
    }] });
    expect((await fetchGrantDetail("grant:one")).fundingScenarios[0].supportRateMaxBps).toBe(10000);
  });

  it("rejects noncanonical call status instead of showing an untrusted decision state", async () => {
    for (const status of ["OPENED", "UNKNOWN", "OPEN ", "", null]) {
      for (const body of [
        { ...detail, status, versions: [{ ...detail.versions[0], status }] },
        { ...detail, versions: [{ ...detail.versions[0], status }] },
      ]) {
        respond(body);
        await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
          code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
        });
      }
    }
    for (const status of ["DRAFT", "ANNOUNCED", "PLANNED", "OPEN", "PAUSED", "CLOSED", "CANCELLED", "ARCHIVED"]) {
      respond({ ...detail, status, versions: [{ ...detail.versions[0], status }] });
      expect((await fetchGrantDetail("grant:one")).status).toBe(status);
    }
  });

  it("rejects unknown verification states at the detail, document and version boundaries", async () => {
    for (const status of ["Ověřeno", "VERIFIED ", "UNKNOWN", "", null]) {
      for (const body of [
        { ...detail, verificationStatus: status, versions: [{ ...detail.versions[0], verificationStatus: status }] },
        { ...detail, evidence: [{ ...detail.evidence[0], verificationStatus: status }] },
        { ...detail, versions: [{ ...detail.versions[0], verificationStatus: status }] },
      ]) {
        respond(body);
        await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
          code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
        });
      }
    }
    for (const status of ["AUTO_EXTRACTED", "PARTIALLY_VERIFIED", "VERIFIED", "NEEDS_REVIEW"]) {
      respond({ ...detail, verificationStatus: status,
        versions: [{ ...detail.versions[0], verificationStatus: status }],
        evidence: [{ ...detail.evidence[0], verificationStatus: status }] });
      expect((await fetchGrantDetail("grant:one")).evidence[0].verificationStatus).toBe(status);
    }
  });

  it("rejects invalid provenance page ranges without inventing a source page", async () => {
    const evidence = detail.evidence[0];
    for (const pages of [
      { pageFrom: 0 }, { pageFrom: -1 }, { pageFrom: 1.5 },
      { pageFrom: Number.MAX_SAFE_INTEGER + 1 }, { pageTo: 0 },
      { pageTo: -1 }, { pageTo: 2.5 },
      { pageFrom: 4, pageTo: 3 },
    ]) {
      respond({ ...detail, evidence: [{ ...evidence, ...pages }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    for (const pages of [
      { pageFrom: null, pageTo: null },
      { pageFrom: 1, pageTo: null },
      { pageFrom: null, pageTo: 2 },
      { pageFrom: 2, pageTo: 2 },
      { pageFrom: 2, pageTo: 3 },
    ]) {
      respond({ ...detail, evidence: [{ ...evidence, ...pages }] });
      expect((await fetchGrantDetail("grant:one")).evidence[0]).toMatchObject(pages);
    }
  });

  it("rejects unknown source presence instead of treating it as observed or missing", async () => {
    for (const presenceState of ["CANCELLED", "", "UNKNOWN", null]) {
      respond({ ...detail, sources: [{ ...detail.sources[0], presenceState }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    for (const presenceState of ["SEEN", "MISSING_CANDIDATE", "CONFIRMED_MISSING"]) {
      respond({ ...detail, sources: [{ ...detail.sources[0], presenceState }] });
      expect((await fetchGrantDetail("grant:one")).sources[0].presenceState).toBe(presenceState);
    }
    respond({ ...detail, sources: [] });
    expect((await fetchGrantDetail("grant:one")).sources).toEqual([]);
  });

  it("preserves source-defined payment modes while rejecting non-string finance data", async () => {
    for (const paymentMode of [false, 0, { mode: "CASH" }]) {
      respond({ ...detail, fundingScenarios: [{ ...detail.fundingScenarios[0], paymentMode }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    for (const paymentMode of [null, "UNKNOWN", "ADVANCE", "REIMBURSEMENT", "MIXED", "CASH"]) {
      respond({ ...detail, fundingScenarios: [{ ...detail.fundingScenarios[0], paymentMode }] });
      expect((await fetchGrantDetail("grant:one")).fundingScenarios[0].paymentMode).toBe(paymentMode);
    }
  });

  it("rejects unknown requirement necessity instead of demoting it to recommended", async () => {
    for (const necessity of ["MANDATORY", "", "UNKNOWN", null]) {
      respond({ ...detail, requirements: [{ ...detail.requirements[0], necessity }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    for (const necessity of ["REQUIRED", "CONDITIONAL", "RECOMMENDED"]) {
      respond({ ...detail, requirements: [{ ...detail.requirements[0], necessity }] });
      expect((await fetchGrantDetail("grant:one")).requirements[0].necessity).toBe(necessity);
    }
    respond({ ...detail, requirements: [], availability: { ...detail.availability, requirements: "UNKNOWN" } });
    expect((await fetchGrantDetail("grant:one")).requirements).toEqual([]);
  });

  it("rejects duplicate collection identities rather than repeating evidence or requirements", async () => {
    const collections = ["deadlines", "fundingScenarios", "requirements", "evidence", "changes"] as const;
    for (const key of collections) {
      const items = detail[key];
      respond({ ...detail, [key]: [items[0], { ...items[0] }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    respond(detail);
    expect((await fetchGrantDetail("grant:one")).evidence).toHaveLength(1);
  });

  it("rejects contradictory availability rather than implying complete requirements or evidence", async () => {
    const invalid = [
      { ...detail, availability: { ...detail.availability, funding: "UNKNOWN" } },
      { ...detail, availability: { ...detail.availability, requirements: "UNKNOWN" } },
      { ...detail, availability: { ...detail.availability, evidence: "SOURCE_ONLY" } },
      { ...detail, fundingScenarios: [] },
      { ...detail, requirements: [] },
      { ...detail, evidence: [] },
    ];
    for (const body of invalid) {
      respond(body);
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    respond({ ...detail, fundingScenarios: [], requirements: [], evidence: [],
      availability: { funding: "UNKNOWN", requirements: "UNKNOWN", evidence: "SOURCE_ONLY" } });
    expect((await fetchGrantDetail("grant:one")).availability.requirements).toBe("UNKNOWN");
  });

  it("rejects a version history that contradicts the displayed current version", async () => {
    const current = detail.versions[0];
    const invalid = [
      { versions: [] },
      { versions: [{ ...current, id: "other" }] },
      { versions: [{ ...current, isCurrent: false }] },
      { versions: [{ ...current, versionNumber: 2 }] },
      { versions: [{ ...current, capturedAt: "2025-01-01T00:00:00Z" }] },
      { versions: [{ ...current, status: "CANCELLED" }] },
      { versions: [{ ...current, verificationStatus: "NEEDS_REVIEW" }] },
      { versions: [{ ...current, submissionCloseAt: "2026-12-31" }] },
      { versions: [current, { ...current, id: "other", versionNumber: 2, isCurrent: true }] },
      { versions: [current, { ...current, isCurrent: false }] },
      { versions: [current, { ...current, id: "other", isCurrent: false }] },
    ];
    for (const change of invalid) {
      respond({ ...detail, ...change });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    respond({ ...detail, versions: [current, { ...current, id: "v0", versionNumber: 0, isCurrent: false }] });
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({ code: "INVALID_GRANT_DETAIL_RESPONSE" });
    respond({ ...detail, versionNumber: 2, versions: [
      { ...current, versionNumber: 2 },
      { ...current, id: "v0", versionNumber: 1, isCurrent: false },
    ] });
    expect((await fetchGrantDetail("grant:one")).versions).toHaveLength(2);
  });

  it("rejects out-of-order history without rejecting a reactivated older current version", async () => {
    const current = detail.versions[0];
    const history = [
      current,
      { ...current, id: "v3", versionNumber: 3, isCurrent: false },
      { ...current, id: "v2", versionNumber: 2, isCurrent: false },
    ];
    respond({ ...detail, versions: history });
    expect((await fetchGrantDetail("grant:one")).versions).toEqual(history);
    respond({ ...detail, versions: [current, history[2], history[1]] });
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
      code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
    });
    respond({ ...detail, versions: [history[1], current, history[2]] });
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
      code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
    });
  });

  it("rejects oversized bounded API collections without silently truncating evidence or history", async () => {
    const capped = {
      ...detail,
      sources: Array.from({ length: 20 }, (_, index) => ({ ...detail.sources[0], sourceCode: `source-${index}` })),
      evidence: Array.from({ length: 100 }, (_, index) => ({ ...detail.evidence[0], id: `e${index}` })),
      changes: Array.from({ length: 20 }, (_, index) => ({ ...detail.changes[0], id: `c${index}` })),
      versions: [detail.versions[0], ...Array.from({ length: 19 }, (_, index) => ({
        ...detail.versions[0], id: `v${20 - index}`, versionNumber: 20 - index, isCurrent: false,
      }))],
    };
    respond(capped);
    expect((await fetchGrantDetail("grant:one")).evidence).toHaveLength(100);
    for (const key of ["sources", "evidence", "changes", "versions"] as const) {
      respond({ ...capped, [key]: [...capped[key], {
        ...capped[key][0], ...(key === "versions" ? { id: "v21", versionNumber: 21, isCurrent: false }
          : key === "sources" ? { sourceCode: "source-21" } : { id: "extra" }),
      }] });
      await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({
        code: "INVALID_GRANT_DETAIL_RESPONSE", status: 200,
      });
    }
    respond({ ...detail, sources: [], evidence: [], changes: [],
      availability: { ...detail.availability, evidence: "SOURCE_ONLY" } });
    expect((await fetchGrantDetail("grant:one")).availability.evidence).toBe("SOURCE_ONLY");
  });

  it("preserves the API error status and rejects malformed error envelopes safely", async () => {
    respond({ error: "GRANT_NOT_FOUND" }, 404);
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({ code: "GRANT_NOT_FOUND", status: 404 });
    respond(null, 503);
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({ code: "GRANT_DETAIL_UNAVAILABLE", status: 503 });
  });
});
