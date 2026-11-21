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
  conditionGroupId: string | null;
  instrumentType: "GRANT" | "LOAN" | "GUARANTEE" | "EQUITY" | "MIXED" | "OTHER";
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
  fundingInstrumentType: GrantFundingScenarioDetail["instrumentType"];
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): boolean {
  return value === null || isString(value);
}

function isPageNumber(value: unknown): boolean {
  return value === null || (typeof value === "number" && Number.isSafeInteger(value) && value > 0);
}

function isPageRange(value: Record<string, unknown>): boolean {
  return value.pageFrom === null || value.pageTo === null
    || (typeof value.pageFrom === "number" && typeof value.pageTo === "number"
      && value.pageFrom <= value.pageTo);
}

function isNonnegativeMinor(value: unknown): boolean {
  return value === null || (typeof value === "number" && Number.isSafeInteger(value) && value >= 0);
}

function isRateBps(value: unknown): boolean {
  return isNonnegativeMinor(value) && (value === null || (typeof value === "number" && value <= 10000));
}

function hasFields(value: unknown, fields: Record<string, (value: unknown) => boolean>): value is Record<string, unknown> {
  return isRecord(value) && Object.entries(fields).every(([key, check]) => Object.hasOwn(value, key) && check(value[key]));
}

function boundsOrdered(value: Record<string, unknown>, lower: string, upper: string): boolean {
  const min = value[lower];
  const max = value[upper];
  return min === null || max === null || (typeof min === "number" && typeof max === "number" && min <= max);
}

function isList(value: unknown, check: (value: unknown) => boolean): boolean {
  return Array.isArray(value) && value.every(check);
}

function hasUniqueIds(value: unknown): boolean {
  return Array.isArray(value)
    && new Set(value.map((item: { id: string }) => item.id)).size === value.length;
}

const instrumentTypes = ["GRANT", "LOAN", "GUARANTEE", "EQUITY", "MIXED", "OTHER"];
const isInstrument = (value: unknown) => instrumentTypes.includes(value as string);
const isVersionNumber = (value: unknown) => Number.isSafeInteger(value) && (value as number) > 0;

function hasConsistentVersions(value: GrantDetailResponse): boolean {
  const current = value.versions.filter((version) => version.isCurrent);
  return current.length === 1
    && current[0].id === value.versionId
    && current[0].versionNumber === value.versionNumber
    && current[0].capturedAt === value.capturedAt
    && current[0].status === value.status
    && current[0].verificationStatus === value.verificationStatus
    && current[0].submissionCloseAt === value.submissionCloseAt
    && new Set(value.versions.map((version) => version.id)).size === value.versions.length
    && new Set(value.versions.map((version) => version.versionNumber)).size === value.versions.length;
}

function isGrantDetailResponse(value: unknown, requestedId: string): value is GrantDetailResponse {
  return hasFields(value, {
    grantCallId: (v) => v === requestedId,
    canonicalCode: isNullableString, canonicalSlug: isString,
    versionId: isString, versionNumber: isVersionNumber, capturedAt: isString,
    title: isString, summary: isString, status: isString, verificationStatus: isString,
    publishedAt: isNullableString, submissionOpenAt: isNullableString,
    submissionCloseAt: isNullableString, applicationUrl: isNullableString,
    officialDetailUrl: isNullableString, currencyCode: isNullableString,
    fundingInstrumentType: isInstrument,
    provider: (v) => hasFields(v, { id: isString, name: isString, type: isString, officialUrl: isNullableString }),
    programme: (v) => hasFields(v, { id: isString, name: isString, fundingOrigin: isString, officialUrl: isNullableString }),
    sources: (v) => isList(v, (item) => hasFields(item, {
      sourceCode: isString, sourceName: isString, canonicalUrl: isString,
      lastSeenAt: isString, presenceState: isString,
    })),
    deadlines: (v) => isList(v, (item) => hasFields(item, {
      id: isString, type: isString, startsAt: isNullableString, endsAt: isNullableString,
      timezone: isNullableString, description: isNullableString, evidenceId: isNullableString,
    })),
    fundingScenarios: (v) => isList(v, (item) => hasFields(item, {
      id: isString, name: isString, conditionGroupId: isNullableString,
      instrumentType: isInstrument, currencyCode: isString,
      supportRateMinBps: isRateBps, supportRateMaxBps: isRateBps,
      grantAmountMinMinor: isNonnegativeMinor, grantAmountMaxMinor: isNonnegativeMinor,
      projectCostMinMinor: isNonnegativeMinor, projectCostMaxMinor: isNonnegativeMinor,
      paymentMode: isNullableString, vatRule: isNullableString,
      advancePaymentAllowed: (x) => x === null || typeof x === "boolean",
      evidenceId: isNullableString,
    }) && boundsOrdered(item, "supportRateMinBps", "supportRateMaxBps")
      && boundsOrdered(item, "grantAmountMinMinor", "grantAmountMaxMinor")
      && boundsOrdered(item, "projectCostMinMinor", "projectCostMaxMinor")),
    requirements: (v) => isList(v, (item) => hasFields(item, {
      id: isString, type: isString, title: isString, description: isNullableString,
      necessity: isString, phase: isNullableString, evidenceId: isNullableString,
    })),
    evidence: (v) => isList(v, (item) => hasFields(item, {
      id: isString, fieldPath: isString, pageFrom: isPageNumber, pageTo: isPageNumber,
      evidenceText: isNullableString, verificationStatus: isString,
      documentTitle: isNullableString, sourceUrl: isString, retrievedAt: isString,
    }) && isPageRange(item)),
    changes: (v) => isList(v, (item) => hasFields(item, {
      id: isString, changeType: isString, severity: isString,
      fieldPath: isNullableString, oldValue: () => true, newValue: () => true, createdAt: isString,
    })),
    versions: (v) => isList(v, (item) => hasFields(item, {
      id: isString, versionNumber: isVersionNumber, capturedAt: isString,
      status: isString, verificationStatus: isString,
      submissionCloseAt: isNullableString, isCurrent: (x) => typeof x === "boolean",
    })),
    availability: (v) => hasFields(v, {
      funding: (x) => x === "AVAILABLE" || x === "UNKNOWN",
      requirements: (x) => x === "AVAILABLE" || x === "UNKNOWN",
      evidence: (x) => x === "AVAILABLE" || x === "SOURCE_ONLY",
    }),
  }) && hasUniqueIds(value.deadlines)
    && hasUniqueIds(value.fundingScenarios)
    && hasUniqueIds(value.requirements)
    && hasUniqueIds(value.evidence)
    && hasUniqueIds(value.changes)
    && isRecord(value.availability)
    && Array.isArray(value.fundingScenarios)
    && (value.fundingScenarios.length > 0) === (value.availability.funding === "AVAILABLE")
    && Array.isArray(value.requirements)
    && (value.requirements.length > 0) === (value.availability.requirements === "AVAILABLE")
    && Array.isArray(value.evidence)
    && (value.evidence.length > 0) === (value.availability.evidence === "AVAILABLE")
    && hasConsistentVersions(value as unknown as GrantDetailResponse);
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
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GrantDetailApiError(
      isRecord(body) && typeof body.error === "string" && body.error ? body.error : "GRANT_DETAIL_UNAVAILABLE",
      response.status,
    );
  }
  if (!isGrantDetailResponse(body, grantCallId)) {
    throw new GrantDetailApiError("INVALID_GRANT_DETAIL_RESPONSE", response.status);
  }
  return body;
}
