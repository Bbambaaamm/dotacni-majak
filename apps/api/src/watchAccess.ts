import type { Env } from "./env";
import { ApiInputError, hashOwnerToken } from "./projectAccess";

const PROJECT_ID_RE = /^prj_[a-f0-9]{32}$/;
const OWNER_TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;
const WATCH_ID_RE = /^wch_[a-f0-9]{32}$/;
const MAX_BODY_BYTES = 4 * 1024;

export interface ProjectWatchRecord {
  id: string;
  projectId: string;
  enabled: boolean;
  minimumMatchBand: "WEAK" | "POSSIBLE" | "VERY_GOOD";
  createdAt: string;
  updatedAt: string;
}

interface WatchRow {
  id: string;
  project_id: string;
  enabled: number;
  minimum_match_band: "WEAK" | "POSSIBLE" | "VERY_GOOD" | null;
  created_at: string;
  updated_at: string;
}

function randomId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

function watchFromRow(row: WatchRow): ProjectWatchRecord {
  return {
    id: row.id,
    projectId: row.project_id,
    enabled: row.enabled === 1,
    minimumMatchBand: row.minimum_match_band ?? "POSSIBLE",
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function assertInputs(projectId: string, ownerToken: string): void {
  if (!PROJECT_ID_RE.test(projectId) || !OWNER_TOKEN_RE.test(ownerToken)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
}

async function ownerHashOrThrow(
  projectId: string,
  ownerToken: string,
  env: Env,
): Promise<string> {
  assertInputs(projectId, ownerToken);
  const ownerHash = await hashOwnerToken(ownerToken);
  const row = await env.DB.prepare(
    `SELECT 1 AS ok
     FROM project_owner_capabilities
     WHERE project_id = ?
       AND token_hash = ?
       AND revoked_at IS NULL
     LIMIT 1`,
  ).bind(projectId, ownerHash).first<{ ok: number }>();
  if (row?.ok !== 1) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
  return ownerHash;
}

async function readWatch(
  projectId: string,
  env: Env,
): Promise<ProjectWatchRecord | null> {
  const row = await env.DB.prepare(
    `SELECT
       id, project_id, enabled, minimum_match_band, created_at, updated_at
     FROM watches
     WHERE project_id = ?
       AND watch_type = 'PROJECT'
     LIMIT 1`,
  ).bind(projectId).first<WatchRow>();
  return row ? watchFromRow(row) : null;
}

export async function getProjectWatch(
  projectId: string,
  ownerToken: string,
  env: Env,
): Promise<ProjectWatchRecord | null> {
  await ownerHashOrThrow(projectId, ownerToken, env);
  return readWatch(projectId, env);
}

export async function enableProjectWatch(
  projectId: string,
  ownerToken: string,
  env: Env,
  now = new Date(),
): Promise<ProjectWatchRecord> {
  await ownerHashOrThrow(projectId, ownerToken, env);
  const timestamp = now.toISOString();
  const watchId = "wch_" + randomId();

  // INSERT OR IGNORE + UPDATE is deliberately idempotent. The partial unique
  // index guarantees only one PROJECT watch per project even under retries.
  const results = await env.DB.batch([
    env.DB.prepare(
      `INSERT OR IGNORE INTO watches(
         id, user_id, watch_type, project_id, grant_call_id,
         ontology_term_id, provider_id, geography_id, filter_json,
         minimum_match_band, enabled, created_at, updated_at
       ) VALUES (?, NULL, 'PROJECT', ?, NULL, NULL, NULL, NULL, NULL, 'POSSIBLE', 1, ?, ?)`,
    ).bind(watchId, projectId, timestamp, timestamp),
    env.DB.prepare(
      `UPDATE watches
       SET enabled = 1, updated_at = ?
       WHERE project_id = ? AND watch_type = 'PROJECT'`,
    ).bind(timestamp, projectId),
  ]);
  if (results.some((result) => !result.success)) {
    throw new Error("PROJECT_WATCH_WRITE_FAILED");
  }
  const watch = await readWatch(projectId, env);
  if (!watch) throw new Error("PROJECT_WATCH_READ_AFTER_WRITE_FAILED");
  return watch;
}

export async function setProjectWatchEnabled(
  projectId: string,
  ownerToken: string,
  enabled: boolean,
  env: Env,
  now = new Date(),
): Promise<ProjectWatchRecord> {
  await ownerHashOrThrow(projectId, ownerToken, env);
  const timestamp = now.toISOString();
  const result = await env.DB.prepare(
    `UPDATE watches
     SET enabled = ?, updated_at = ?
     WHERE project_id = ? AND watch_type = 'PROJECT'`,
  ).bind(enabled ? 1 : 0, timestamp, projectId).run();
  if (!result.success) throw new Error("PROJECT_WATCH_UPDATE_FAILED");
  if ((result.meta?.changes ?? 0) !== 1) {
    throw new ApiInputError("PROJECT_WATCH_NOT_FOUND", 404);
  }
  const watch = await readWatch(projectId, env);
  if (!watch) throw new Error("PROJECT_WATCH_READ_AFTER_UPDATE_FAILED");
  return watch;
}

export async function deleteProjectWatch(
  projectId: string,
  ownerToken: string,
  env: Env,
): Promise<void> {
  await ownerHashOrThrow(projectId, ownerToken, env);
  await env.DB.prepare(
    `DELETE FROM watches
     WHERE project_id = ? AND watch_type = 'PROJECT'`,
  ).bind(projectId).run();
  // Authorized delete is intentionally idempotent.
}

export async function parseWatchEnabled(request: Request): Promise<boolean> {
  const declared = request.headers.get("content-length");
  if (declared && Number(declared) > MAX_BODY_BYTES) {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES) {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new ApiInputError("INVALID_JSON");
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new ApiInputError("INVALID_WATCH_INPUT");
  }
  const enabled = (body as Record<string, unknown>).enabled;
  if (typeof enabled !== "boolean") {
    throw new ApiInputError("INVALID_WATCH_ENABLED");
  }
  return enabled;
}

export function projectWatchPath(pathname: string): string | null {
  const match = pathname.match(/^\/projects\/(prj_[a-f0-9]{32})\/watch$/);
  return match?.[1] ?? null;
}

export function isWatchId(value: string): boolean {
  return WATCH_ID_RE.test(value);
}
