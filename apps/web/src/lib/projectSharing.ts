import { apiUrl } from "./sharedProject";

const PROJECT_ID_RE = /^prj_[a-f0-9]{32}$/;
const SHARE_ID_RE = /^shr_[a-f0-9]{32}$/;
const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;

export interface AnonymousProjectInput {
  title: string | null;
  naturalLanguageIntent: string;
  currencyCode?: string;
  estimatedTotalBudgetMinor?: number | null;
  plannedStart?: string | null;
  plannedEnd?: string | null;
}

export interface OwnedProject {
  projectId: string;
  ownerCapability: string;
}

export interface ShareLink {
  shareId: string;
  token: string;
  sharePath: string;
  expiresAt: string;
}

export class ProjectSharingError extends Error {
  constructor(
    public readonly code: string,
    public readonly status?: number,
  ) {
    super(code);
  }
}

export async function createAnonymousProject(
  input: AnonymousProjectInput,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<OwnedProject> {
  const response = await fetcher(apiUrl("/projects", baseUrl), {
    method: "POST",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      ...input,
      currencyCode: input.currencyCode ?? "CZK",
    }),
    credentials: "omit",
    cache: "no-store",
    referrerPolicy: "no-referrer",
  });
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new ProjectSharingError(errorCode(payload), response.status);
  }

  const projectId = stringField(payload, "projectId");
  const ownerCapability = stringField(payload, "ownerCapability");
  if (!PROJECT_ID_RE.test(projectId) || !TOKEN_RE.test(ownerCapability)) {
    throw new ProjectSharingError("INVALID_PROJECT_RESPONSE");
  }
  return { projectId, ownerCapability };
}

export async function createReadOnlyShare(
  projectId: string,
  ownerCapability: string,
  expiresInDays: number,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<ShareLink> {
  assertProjectOwner(projectId, ownerCapability);
  if (!Number.isSafeInteger(expiresInDays) || expiresInDays < 1 || expiresInDays > 365) {
    throw new ProjectSharingError("INVALID_SHARE_EXPIRY");
  }

  const response = await fetcher(
    apiUrl(`/projects/${encodeURIComponent(projectId)}/shares`, baseUrl),
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        authorization: `Bearer ${ownerCapability}`,
      },
      body: JSON.stringify({ expiresInDays }),
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    },
  );
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new ProjectSharingError(errorCode(payload), response.status);
  }

  const shareId = stringField(payload, "shareId");
  const token = stringField(payload, "token");
  const sharePath = stringField(payload, "sharePath");
  const expiresAt = stringField(payload, "expiresAt");
  if (
    !SHARE_ID_RE.test(shareId)
    || !TOKEN_RE.test(token)
    || sharePath !== `/s/${token}`
    || Number.isNaN(Date.parse(expiresAt))
  ) {
    throw new ProjectSharingError("INVALID_SHARE_RESPONSE");
  }
  return { shareId, token, sharePath, expiresAt };
}

export async function revokeReadOnlyShare(
  projectId: string,
  shareId: string,
  ownerCapability: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<void> {
  assertProjectOwner(projectId, ownerCapability);
  if (!SHARE_ID_RE.test(shareId)) {
    throw new ProjectSharingError("INVALID_SHARE_ID");
  }

  const response = await fetcher(
    apiUrl(
      `/projects/${encodeURIComponent(projectId)}/shares/${encodeURIComponent(shareId)}`,
      baseUrl,
    ),
    {
      method: "DELETE",
      headers: { authorization: `Bearer ${ownerCapability}` },
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    },
  );
  if (response.status !== 204) {
    const payload = await safeJson(response);
    throw new ProjectSharingError(errorCode(payload), response.status);
  }
}

export function absoluteShareUrl(
  sharePath: string,
  origin = window.location.origin,
): string {
  if (!/^\/s\/[A-Za-z0-9_-]{40,128}$/.test(sharePath)) {
    throw new ProjectSharingError("INVALID_SHARE_PATH");
  }
  return new URL(sharePath, origin).toString();
}

function assertProjectOwner(projectId: string, ownerCapability: string): void {
  if (!PROJECT_ID_RE.test(projectId) || !TOKEN_RE.test(ownerCapability)) {
    throw new ProjectSharingError("OWNER_CAPABILITY_INVALID");
  }
}

async function safeJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function errorCode(payload: unknown): string {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const value = (payload as Record<string, unknown>).error;
    if (typeof value === "string") return value;
  }
  return "REQUEST_FAILED";
}

function stringField(payload: unknown, field: string): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ProjectSharingError("INVALID_API_RESPONSE");
  }
  const value = (payload as Record<string, unknown>)[field];
  if (typeof value !== "string") {
    throw new ProjectSharingError("INVALID_API_RESPONSE");
  }
  return value;
}
