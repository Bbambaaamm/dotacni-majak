import type { Env } from "./env";
import { ApiInputError, hashOwnerToken } from "./projectAccess";

const PROJECT_ID = /^prj_[a-f0-9]{32}$/;
const OWNER_TOKEN = /^[A-Za-z0-9_-]{40,128}$/;

export async function projectNotifications(
  projectId: string, token: string, env: Env,
): Promise<{ notifications: Array<{
  id: string; title: string; body: string; grantCallId: string;
  status: string; createdAt: string;
}> }> {
  if (!PROJECT_ID.test(projectId) || !OWNER_TOKEN.test(token)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
  const ownerHash = await hashOwnerToken(token);
  const owner = await env.DB.prepare(
    `SELECT 1 AS ok FROM project_owner_capabilities
     WHERE project_id=? AND token_hash=? AND revoked_at IS NULL`,
  ).bind(projectId, ownerHash).first<{ ok: number }>();
  if (owner?.ok !== 1) throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  type NotificationRow = {
    id: string; title: string; body: string; status: string;
    created_at: string; grant_call_id: string;
  };
  const rows = await env.DB.prepare(
    `SELECT n.id,n.title,n.body,n.status,n.created_at,g.id AS grant_call_id
     FROM notifications n
     JOIN watches w ON w.id=n.watch_id
     JOIN grant_call_versions v ON v.id=n.grant_call_version_id
     JOIN grant_calls g ON g.id=v.grant_call_id AND g.current_version_id=v.id
     WHERE w.project_id=? AND n.user_id=('anonymous:' || ?)
       AND n.channel='IN_APP' AND n.status IN ('SENT','READ')
     ORDER BY n.created_at DESC,n.id DESC LIMIT 50`,
  ).bind(projectId, projectId).all<NotificationRow>();
  return { notifications: ((rows.results ?? []) as NotificationRow[]).map((row) => ({
    id: row.id, title: row.title, body: row.body, status: row.status,
    createdAt: row.created_at, grantCallId: row.grant_call_id,
  })) };
}

export function notificationsProjectId(path: string): string | null {
  return path.match(/^\/projects\/(prj_[a-f0-9]{32})\/notifications$/)?.[1] ?? null;
}
