import type { D1PreparedStatementLike, Env } from "./env";
import { hashShareToken } from "./share";

const OWNER_TOKEN_DOMAIN = "dotacni-majak-project-owner-v1\0";
const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;
const MAX_BODY_BYTES = 16 * 1024;
const DEFAULT_SHARE_DAYS = 30;
const MAX_SHARE_DAYS = 365;

export interface CreateProjectInput {
  title: string | null;
  naturalLanguageIntent: string;
  currencyCode: string;
  estimatedTotalBudgetMinor: number | null;
  plannedStart: string | null;
  plannedEnd: string | null;
}

export class ApiInputError extends Error {
  constructor(
    public readonly code: string,
    public readonly status = 400,
  ) {
    super(code);
  }
}

export function bearerToken(request: Request): string | null {
  const authorization = request.headers.get("authorization");
  if (!authorization) return null;
  const match = authorization.match(/^Bearer\s+([A-Za-z0-9_-]{40,128})$/);
  return match?.[1] ?? null;
}

export async function parseProjectInput(request: Request): Promise<CreateProjectInput> {
  const raw = await boundedJsonBody(request);
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new ApiInputError("INVALID_PROJECT");
  }
  const value = raw as Record<string, unknown>;
  const intent = typeof value.naturalLanguageIntent === "string"
    ? value.naturalLanguageIntent.trim()
    : "";
  if (!intent || intent.length > 4000) {
    throw new ApiInputError("INVALID_PROJECT_INTENT");
  }

  const title = value.title == null
    ? null
    : typeof value.title === "string"
      ? value.title.trim()
      : null;
  if (title !== null && (title.length === 0 || title.length > 200)) {
    throw new ApiInputError("INVALID_PROJECT_TITLE");
  }

  const currencyCode = typeof value.currencyCode === "string"
    ? value.currencyCode.trim().toUpperCase()
    : "CZK";
  if (!/^[A-Z]{3}$/.test(currencyCode)) {
    throw new ApiInputError("INVALID_CURRENCY");
  }

  const budget = value.estimatedTotalBudgetMinor == null
    ? null
    : value.estimatedTotalBudgetMinor;
  if (
    budget !== null
    && (
      typeof budget !== "number"
      || !Number.isSafeInteger(budget)
      || budget < 0
    )
  ) {
    throw new ApiInputError("INVALID_PROJECT_BUDGET");
  }

  const plannedStart = optionalDate(value.plannedStart, "INVALID_PLANNED_START");
  const plannedEnd = optionalDate(value.plannedEnd, "INVALID_PLANNED_END");
  if (plannedStart && plannedEnd && plannedStart > plannedEnd) {
    throw new ApiInputError("INVALID_PROJECT_DATES");
  }

  return {
    title,
    naturalLanguageIntent: intent,
    currencyCode,
    estimatedTotalBudgetMinor: budget as number | null,
    plannedStart,
    plannedEnd,
  };
}

export async function createAnonymousProject(
  input: CreateProjectInput,
  env: Env,
  now = new Date(),
): Promise<{ projectId: string; ownerCapability: string }> {
  const projectId = "prj_" + randomId();
  const ownerCapability = randomToken();
  const ownerHash = await hashOwnerToken(ownerCapability);
  const timestamp = now.toISOString();
  const principal = `anonymous:${projectId}`;
  const auditId = "poc_" + randomId();

  const statements = [
    env.DB.prepare(
      `INSERT INTO projects(
        id, owner_user_id, title, natural_language_intent,
        estimated_total_budget_minor, currency_code, planned_start, planned_end,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      projectId,
      principal,
      input.title,
      input.naturalLanguageIntent,
      input.estimatedTotalBudgetMinor,
      input.currencyCode,
      input.plannedStart,
      input.plannedEnd,
      timestamp,
      timestamp,
    ),
    env.DB.prepare(
      `INSERT INTO project_owner_capabilities(
        project_id, token_hash, generation, created_at
      ) VALUES (?, ?, 1, ?)`,
    ).bind(projectId, ownerHash, timestamp),
    env.DB.prepare(
      `INSERT INTO project_owner_audit_events(
        id, project_id, event_type, created_at
      ) VALUES (?, ?, 'CREATED', ?)`,
    ).bind(auditId, projectId, timestamp),
  ];

  const results = await env.DB.batch(statements);
  if (results.length !== 3 || results.some((result) => !result.success)) {
    throw new Error("PROJECT_CREATE_TRANSACTION_FAILED");
  }
  return { projectId, ownerCapability };
}

export async function createProjectShare(
  projectId: string,
  ownerToken: string,
  env: Env,
  *,
  expiresInDays = DEFAULT_SHARE_DAYS,
  now = new Date(),
): Promise<{ shareId: string; token: string; expiresAt: string }> {
  assertProjectId(projectId);
  if (!TOKEN_RE.test(ownerToken)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
  if (
    !Number.isSafeInteger(expiresInDays)
    || expiresInDays < 1
    || expiresInDays > MAX_SHARE_DAYS
  ) {
    throw new ApiInputError("INVALID_SHARE_EXPIRY");
  }

  const ownerHash = await hashOwnerToken(ownerToken);
  const shareToken = randomToken();
  const shareHash = await hashShareToken(shareToken);
  const shareId = "shr_" + randomId();
  const auditId = "sha_" + randomId();
  const timestamp = now.toISOString();
  const expiresAt = new Date(
    now.getTime() + expiresInDays * 24 * 60 * 60 * 1000,
  ).toISOString();

  const insertShare = env.DB.prepare(
    `INSERT INTO project_share_links(
       id, project_id, owner_user_id, token_hash, scope, created_at, expires_at
     )
     SELECT ?, p.id, p.owner_user_id, ?, 'PROJECT_READ_ONLY', ?, ?
     FROM projects AS p
     INNER JOIN project_owner_capabilities AS c ON c.project_id = p.id
     WHERE p.id = ?
       AND c.token_hash = ?
       AND c.revoked_at IS NULL`,
  ).bind(
    shareId,
    shareHash,
    timestamp,
    expiresAt,
    projectId,
    ownerHash,
  );

  const auditShare = env.DB.prepare(
    `INSERT INTO share_audit_events(
       id, share_link_id, project_id, actor_user_id, event_type, created_at
     )
     SELECT ?, s.id, s.project_id, s.owner_user_id, 'CREATED', ?
     FROM project_share_links AS s
     WHERE s.id = ?`,
  ).bind(auditId, timestamp, shareId);

  const results = await env.DB.batch([insertShare, auditShare]);
  const changes = results[0]?.meta?.changes ?? 0;
  if (!results.every((result) => result.success) || changes !== 1) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }

  return { shareId, token: shareToken, expiresAt };
}

export async function revokeProjectShare(
  projectId: string,
  shareId: string,
  ownerToken: string,
  env: Env,
  now = new Date(),
): Promise<void> {
  assertProjectId(projectId);
  if (!/^shr_[a-f0-9]{32}$/.test(shareId) || !TOKEN_RE.test(ownerToken)) {
    return;
  }

  const ownerHash = await hashOwnerToken(ownerToken);
  const timestamp = now.toISOString();
  const auditId = "sha_" + randomId();

  const revoke = env.DB.prepare(
    `UPDATE project_share_links
     SET revoked_at = ?
     WHERE id = ?
       AND project_id = ?
       AND revoked_at IS NULL
       AND EXISTS (
         SELECT 1 FROM project_owner_capabilities AS c
         WHERE c.project_id = ?
           AND c.token_hash = ?
           AND c.revoked_at IS NULL
       )`,
  ).bind(timestamp, shareId, projectId, projectId, ownerHash);

  const audit = env.DB.prepare(
    `INSERT INTO share_audit_events(
       id, share_link_id, project_id, actor_user_id, event_type, created_at
     )
     SELECT ?, s.id, s.project_id, s.owner_user_id, 'REVOKED', ?
     FROM project_share_links AS s
     WHERE s.id = ?
       AND s.project_id = ?
       AND s.revoked_at = ?`,
  ).bind(auditId, timestamp, shareId, projectId, timestamp);

  await env.DB.batch([revoke, audit]);
  // Deliberately idempotent/non-disclosing: invalid project/token/share returns
  // the same external 204 as an already-revoked share.
}

export async function rotateOwnerCapability(
  projectId: string,
  ownerToken: string,
  env: Env,
  now = new Date(),
): Promise<string> {
  assertProjectId(projectId);
  if (!TOKEN_RE.test(ownerToken)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
  const oldHash = await hashOwnerToken(ownerToken);
  const newToken = randomToken();
  const newHash = await hashOwnerToken(newToken);
  const timestamp = now.toISOString();
  const auditId = "poc_" + randomId();

  const update = env.DB.prepare(
    `UPDATE project_owner_capabilities
     SET token_hash = ?,
         generation = generation + 1,
         rotated_at = ?,
         last_used_at = ?
     WHERE project_id = ?
       AND token_hash = ?
       AND revoked_at IS NULL`,
  ).bind(newHash, timestamp, timestamp, projectId, oldHash);

  const audit = env.DB.prepare(
    `INSERT INTO project_owner_audit_events(id, project_id, event_type, created_at)
     SELECT ?, c.project_id, 'ROTATED', ?
     FROM project_owner_capabilities AS c
     WHERE c.project_id = ?
       AND c.token_hash = ?`,
  ).bind(auditId, timestamp, projectId, newHash);

  const results = await env.DB.batch([update, audit]);
  const changes = results[0]?.meta?.changes ?? 0;
  if (!results.every((result) => result.success) || changes !== 1) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
  return newToken;
}

export async function revokeOwnerCapability(
  projectId: string,
  ownerToken: string,
  env: Env,
  now = new Date(),
): Promise<void> {
  assertProjectId(projectId);
  if (!TOKEN_RE.test(ownerToken)) return;
  const ownerHash = await hashOwnerToken(ownerToken);
  const timestamp = now.toISOString();
  const auditId = "poc_" + randomId();

  const update = env.DB.prepare(
    `UPDATE project_owner_capabilities
     SET revoked_at = ?, last_used_at = ?
     WHERE project_id = ?
       AND token_hash = ?
       AND revoked_at IS NULL`,
  ).bind(timestamp, timestamp, projectId, ownerHash);

  const audit = env.DB.prepare(
    `INSERT INTO project_owner_audit_events(id, project_id, event_type, created_at)
     SELECT ?, c.project_id, 'REVOKED', ?
     FROM project_owner_capabilities AS c
     WHERE c.project_id = ?
       AND c.revoked_at = ?`,
  ).bind(auditId, timestamp, projectId, timestamp);

  await env.DB.batch([update, audit]);
}

export async function parseShareOptions(request: Request): Promise<number> {
  if (!request.headers.get("content-length") && request.body === null) {
    return DEFAULT_SHARE_DAYS;
  }
  const body = await boundedJsonBody(request);
  if (body == null) return DEFAULT_SHARE_DAYS;
  if (typeof body !== "object" || Array.isArray(body)) {
    throw new ApiInputError("INVALID_SHARE_OPTIONS");
  }
  const days = (body as Record<string, unknown>).expiresInDays;
  if (days == null) return DEFAULT_SHARE_DAYS;
  if (!Number.isSafeInteger(days) || (days as number) < 1 || (days as number) > MAX_SHARE_DAYS) {
    throw new ApiInputError("INVALID_SHARE_EXPIRY");
  }
  return days as number;
}

async function boundedJsonBody(request: Request): Promise<unknown> {
  const declared = request.headers.get("content-length");
  if (declared && Number(declared) > MAX_BODY_BYTES) {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES) {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiInputError("INVALID_JSON");
  }
}

function optionalDate(value: unknown, code: string): string | null {
  if (value == null || value === "") return null;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new ApiInputError(code);
  }
  const parsed = new Date(value + "T00:00:00Z");
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new ApiInputError(code);
  }
  return value;
}

function assertProjectId(projectId: string): void {
  if (!/^prj_[a-f0-9]{32}$/.test(projectId)) {
    throw new ApiInputError("PROJECT_NOT_FOUND", 404);
  }
}

export async function hashOwnerToken(token: string): Promise<string> {
  const bytes = new TextEncoder().encode(OWNER_TOKEN_DOMAIN + token);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return hex(digest);
}

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

function randomId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/g, "");
}

function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}
