import { describe, expect, it, vi } from "vitest";
import { answerApplicantType, loadProjectEligibility } from "./projectEligibility";

const token = "A".repeat(43);
const grant = "grant:e2e:open";
const snapshot = {
  grantCallId: grant, versionId: "gcv-e2e-open", ruleSetId: "e2e-rule-set-open",
  status: "NEEDS_INFORMATION", rootResult: "UNKNOWN", reason: "EVALUATED",
  conditions: [{ conditionId: "e2e-applicant-type", attributeKey: "applicant.type", result: "UNKNOWN", evidenceId: "e2e-fe-summary" }],
  missingAttributes: ["applicant.type"], blockers: [],
};

describe("owner-only eligibility client", () => {
  it("requests a fresh version using only the authorization header, without credentials in URL", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(snapshot), { status: 200 }));
    expect(await loadProjectEligibility(grant, token, undefined, fetcher as typeof fetch)).toMatchObject(snapshot);
    const [url, options] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/grants/grant%3Ae2e%3Aopen/eligibility");
    expect(url).not.toContain(token);
    expect(options).toMatchObject({ cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" });
    expect(options.headers).toMatchObject({ authorization: `Bearer ${token}` });
  });

  it("fails closed for bad capability, unavailable API, and malformed result", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(snapshot)));
    await expect(loadProjectEligibility(grant, "bad", undefined, fetcher as typeof fetch)).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
    await expect(loadProjectEligibility(grant, token, undefined,
      vi.fn(async () => new Response("{}", { status: 503 })) as typeof fetch)).rejects.toThrow();
    await expect(loadProjectEligibility(grant, token, undefined,
      vi.fn(async () => new Response(JSON.stringify({ ...snapshot, grantCallId: "other" }))) as typeof fetch)).rejects.toThrow();
  });

  it("writes only the declared applicant type and never treats it as verified", async () => {
    const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
    await answerApplicantType("MUNICIPALITY", token, fetcher as typeof fetch);
    const [url, options] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/applicant-profile");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body as string)).toEqual({ applicantType: "MUNICIPALITY" });
    expect(options.headers).toMatchObject({ authorization: `Bearer ${token}` });
    await expect(answerApplicantType("BUSINESS", token,
      vi.fn(async () => new Response("{}", { status: 503 })) as typeof fetch)).rejects.toThrow();
  });
});
