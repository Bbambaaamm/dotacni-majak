import { apiUrl } from "./sharedProject";

const PROJECT_ID_RE = /^prj_[a-f0-9]{32}$/;
const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;

export interface ProjectWatchRecord {
  id: string;
  projectId: string;
  enabled: boolean;
  minimumMatchBand: "WEAK" | "POSSIBLE" | "VERY_GOOD";
  createdAt: string;
  updatedAt: string;
}

export class ProjectWatchError extends Error {
  constructor(
    public readonly code: string,
    public readonly status?: number,
  ) {
    super(code);
  }
}

export async function getProjectWatch(
  projectId: string,
  ownerCapability: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<ProjectWatchRecord | null> {
  assertOwner(projectId, ownerCapability);
  const response = await fetcher(
    apiUrl(`/projects/${encodeURIComponent(projectId)}/watch`, baseUrl),
    {
      method: "GET",
      headers: {
        accept: "application/json",
        authorization: `Bearer ${ownerCapability}`,
      },
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    },
  );
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new ProjectWatchError(errorCode(payload), response.status);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ProjectWatchError("INVALID_WATCH_RESPONSE");
  }
  const watch = (payload as Record<string, unknown>).watch;
  if (watch === null) return null;
  return parseWatch(watch);
}

export async function enableProjectWatch(
  projectId: string,
  ownerCapability: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<ProjectWatchRecord> {
  return mutateWatch(
    projectId,
    ownerCapability,
    { method: "POST" },
    fetcher,
    baseUrl,
  );
}

export async function setProjectWatchEnabled(
  projectId: string,
  ownerCapability: string,
  enabled: boolean,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<ProjectWatchRecord> {
  return mutateWatch(
    projectId,
    ownerCapability,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled }),
    },
    fetcher,
    baseUrl,
  );
}

export async function deleteProjectWatch(
  projectId: string,
  ownerCapability: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<void> {
  assertOwner(projectId, ownerCapability);
  const response = await fetcher(
    apiUrl(`/projects/${encodeURIComponent(projectId)}/watch`, baseUrl),
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
    throw new ProjectWatchError(errorCode(payload), response.status);
  }
}

async function mutateWatch(
  projectId: string,
  ownerCapability: string,
  init: RequestInit,
  fetcher: typeof fetch,
  baseUrl?: string,
): Promise<ProjectWatchRecord> {
  assertOwner(projectId, ownerCapability);
  const response = await fetcher(
    apiUrl(`/projects/${encodeURIComponent(projectId)}/watch`, baseUrl),
    {
      ...init,
      headers: {
        accept: "application/json",
        authorization: `Bearer ${ownerCapability}`,
        ...(init.headers ?? {}),
      },
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    },
  );
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new ProjectWatchError(errorCode(payload), response.status);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ProjectWatchError("INVALID_WATCH_RESPONSE");
  }
  return parseWatch((payload as Record<string, unknown>).watch);
}

function parseWatch(value: unknown): ProjectWatchRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProjectWatchError("INVALID_WATCH_RESPONSE");
  }
  const row = value as Record<string, unknown>;
  if (
    typeof row.id !== "string"
    || typeof row.projectId !== "string"
    || typeof row.enabled !== "boolean"
    || typeof row.minimumMatchBand !== "string"
    || typeof row.createdAt !== "string"
    || typeof row.updatedAt !== "string"
  ) {
    throw new ProjectWatchError("INVALID_WATCH_RESPONSE");
  }
  if (!["WEAK", "POSSIBLE", "VERY_GOOD"].includes(row.minimumMatchBand)) {
    throw new ProjectWatchError("INVALID_WATCH_RESPONSE");
  }
  return row as unknown as ProjectWatchRecord;
}

function assertOwner(projectId: string, ownerCapability: string): void {
  if (!PROJECT_ID_RE.test(projectId) || !TOKEN_RE.test(ownerCapability)) {
    throw new ProjectWatchError("OWNER_CAPABILITY_INVALID");
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
