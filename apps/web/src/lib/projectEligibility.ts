import { apiUrl } from "./sharedProject";
import type { ApplicantProfileType } from "./applicantProfile";

export type EligibilityStatus = "ELIGIBLE" | "LIKELY_ELIGIBLE" | "NEEDS_INFORMATION" | "INELIGIBLE" | "NEEDS_REVIEW";
export interface EligibilitySnapshot {
  grantCallId: string;
  versionId: string;
  ruleSetId: string | null;
  status: EligibilityStatus;
  rootResult: "PASS" | "FAIL" | "UNKNOWN" | "ERROR" | "NOT_APPLICABLE";
  reason: string;
  missingAttributes: string[];
  blockers: string[];
  conditions: Array<{ conditionId: string; attributeKey: string; result: string; evidenceId: string | null }>;
}

const statuses = new Set<EligibilityStatus>(["ELIGIBLE", "LIKELY_ELIGIBLE", "NEEDS_INFORMATION", "INELIGIBLE", "NEEDS_REVIEW"]);
const results = new Set(["PASS", "FAIL", "UNKNOWN", "ERROR", "NOT_APPLICABLE"]);
const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;

function assertToken(token: string): void {
  if (!TOKEN_RE.test(token)) throw new Error("OWNER_CAPABILITY_INVALID");
}

function parseSnapshot(value: unknown, grantCallId: string): EligibilitySnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("INVALID_ELIGIBILITY_RESPONSE");
  const snapshot = value as EligibilitySnapshot;
  if (snapshot.grantCallId !== grantCallId || typeof snapshot.versionId !== "string" || !snapshot.versionId
    || (snapshot.ruleSetId !== null && typeof snapshot.ruleSetId !== "string")
    || !statuses.has(snapshot.status) || !results.has(snapshot.rootResult)
    || typeof snapshot.reason !== "string"
    || !Array.isArray(snapshot.missingAttributes) || !snapshot.missingAttributes.every((key) => typeof key === "string")
    || !Array.isArray(snapshot.blockers) || !snapshot.blockers.every((id) => typeof id === "string")
    || !Array.isArray(snapshot.conditions) || !snapshot.conditions.every((condition) => condition
      && typeof condition.conditionId === "string" && typeof condition.attributeKey === "string"
      && results.has(condition.result) && (condition.evidenceId === null || typeof condition.evidenceId === "string"))) {
    throw new Error("INVALID_ELIGIBILITY_RESPONSE");
  }
  return snapshot;
}

export async function loadProjectEligibility(
  grantCallId: string, ownerCapability: string, signal?: AbortSignal,
  fetcher: typeof fetch = fetch, baseUrl?: string,
): Promise<EligibilitySnapshot> {
  assertToken(ownerCapability);
  const response = await fetcher(apiUrl(`/grants/${encodeURIComponent(grantCallId)}/eligibility`, baseUrl), {
    headers: { accept: "application/json", authorization: `Bearer ${ownerCapability}` },
    credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer", signal,
  });
  if (!response.ok) throw new Error("ELIGIBILITY_UNAVAILABLE");
  return parseSnapshot(await response.json(), grantCallId);
}

export async function answerApplicantType(
  applicantType: Exclude<ApplicantProfileType, "UNKNOWN">,
  ownerCapability: string, fetcher: typeof fetch = fetch, baseUrl?: string,
): Promise<void> {
  assertToken(ownerCapability);
  const response = await fetcher(apiUrl("/applicant-profile", baseUrl), {
    method: "PUT",
    headers: { accept: "application/json", "content-type": "application/json", authorization: `Bearer ${ownerCapability}` },
    body: JSON.stringify({ applicantType }),
    credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new Error("PROFILE_UPDATE_FAILED");
}
