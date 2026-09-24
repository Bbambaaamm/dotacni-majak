export interface GrantSourceRef {
  sourceCode: string;
  sourceName: string;
  canonicalUrl: string;
  lastSeenAt: string;
  presenceState: string;
}

export interface GrantDeadlineDetail {
  id: string;
  type: string;
  startsAt: string | null;
  endsAt: string | null;
  timezone: string | null;
  description: string | null;
  evidenceId: string | null;
}

export interface GrantFundingScenarioDetail {
  id: string;
  name: string;
  currencyCode: string;
  supportRateMinBps: number | null;
  supportRateMaxBps: number | null;
  grantAmountMinMinor: number | null;
  grantAmountMaxMinor: number | null;
  projectCostMinMinor: number | null;
  projectCostMaxMinor: number | null;
  paymentMode: string | null;
  vatRule: string | null;
  advancePaymentAllowed: boolean | null;
  evidenceId: string | null;
}

export interface GrantRequirementDetail {
  id: string;
  type: string;
  title: string;
  description: string | null;
  necessity: string;
  phase: string | null;
  evidenceId: string | null;
}

export interface GrantEvidenceDetail {
  id: string;
  fieldPath: string;
  pageFrom: number | null;
  pageTo: number | null;
  evidenceText: string | null;
  verificationStatus: string;
  documentTitle: string | null;
  sourceUrl: string;
  retrievedAt: string;
}

export interface GrantChangeDetail {
  id: string;
  changeType: string;
  severity: string;
  fieldPath: string | null;
  oldValue: unknown;
  newValue: unknown;
  createdAt: string;
}

export interface GrantVersionSummary {
  id: string;
  versionNumber: number;
  capturedAt: string;
  status: string;
  verificationStatus: string;
  submissionCloseAt: string | null;
  isCurrent: boolean;
}

export interface GrantDetailResponse {
  grantCallId: string;
  canonicalCode: string | null;
  canonicalSlug: string;
  versionId: string;
  versionNumber: number;
  capturedAt: string;
  title: string;
  summary: string;
  status: string;
  verificationStatus: string;
  publishedAt: string | null;
  submissionOpenAt: string | null;
  submissionCloseAt: string | null;
  applicationUrl: string | null;
  officialDetailUrl: string | null;
  currencyCode: string | null;
  provider: {
    id: string;
    name: string;
    type: string;
    officialUrl: string | null;
  };
  programme: {
    id: string;
    name: string;
    fundingOrigin: string;
    officialUrl: string | null;
  };
  sources: GrantSourceRef[];
  deadlines: GrantDeadlineDetail[];
  fundingScenarios: GrantFundingScenarioDetail[];
  requirements: GrantRequirementDetail[];
  evidence: GrantEvidenceDetail[];
  changes: GrantChangeDetail[];
  versions: GrantVersionSummary[];
  availability: {
    funding: "AVAILABLE" | "UNKNOWN";
    requirements: "AVAILABLE" | "UNKNOWN";
    evidence: "AVAILABLE" | "SOURCE_ONLY";
  };
}

export class GrantDetailApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
  }
}

export async function fetchGrantDetail(
  grantCallId: string,
  signal?: AbortSignal,
): Promise<GrantDetailResponse> {
  const response = await fetch(
    `/api/grants/${encodeURIComponent(grantCallId)}`,
    {
      headers: { accept: "application/json" },
      signal,
    },
  );
  const body = await response.json().catch(() => ({})) as
    | GrantDetailResponse
    | { error?: string };
  if (!response.ok) {
    throw new GrantDetailApiError(
      "error" in body && body.error ? body.error : "GRANT_DETAIL_UNAVAILABLE",
      response.status,
    );
  }
  return body as GrantDetailResponse;
}
