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

  it("preserves the API error status and rejects malformed error envelopes safely", async () => {
    respond({ error: "GRANT_NOT_FOUND" }, 404);
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({ code: "GRANT_NOT_FOUND", status: 404 });
    respond(null, 503);
    await expect(fetchGrantDetail("grant:one")).rejects.toMatchObject({ code: "GRANT_DETAIL_UNAVAILABLE", status: 503 });
  });
});
