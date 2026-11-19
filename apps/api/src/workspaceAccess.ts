import type { Env } from "./env";
import { ApiInputError, hashOwnerToken } from "./projectAccess";

const PROJECT = /^prj_[a-f0-9]{32}$/;
const WORKSPACE = /^wsp_[a-f0-9]{32}$/;
const TASK = /^tsk_[a-f0-9]{32}$/;
const TOKEN = /^[A-Za-z0-9_-]{40,128}$/;

type Version = { id: string; title: string; status: string; submission_close_at: string | null; official_detail_url: string | null; captured_at: string };
type Requirement = { id: string; requirement_type: string; title: string; necessity: string; evidence_id: string | null };
type Task = { id: string; title: string; source: string; necessity: string; status: string; blocking: number; priority: number; reference_id: string | null; reason_code: string | null };
type Workspace = { id: string; project_id: string; grant_call_id: string; baseline_grant_version_id: string; status: string };
type ChangeRow = { field_path: string | null; old_value_json: string | null; new_value_json: string | null; evidence_id: string | null };

function displayChangeValue(value: string | null): string | null {
  if (value === null) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed === null ? null : typeof parsed === "string" ? parsed : JSON.stringify(parsed);
  } catch { return value; }
}

function safeSourceUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch { return null; }
}

export function workspacePath(path: string): { projectId: string; workspaceId?: string; taskId?: string } | null {
  const match = path.match(/^\/projects\/(prj_[a-f0-9]{32})\/workspaces(?:\/(wsp_[a-f0-9]{32})(?:\/tasks\/(tsk_[a-f0-9]{32}))?)?$/);
  return match ? { projectId: match[1], workspaceId: match[2], taskId: match[3] } : null;
}

export async function authorizeProjectWorkspace(projectId: string, token: string | null, env: Env): Promise<string> {
  return authorize(projectId, token, env);
}

async function authorize(projectId: string, token: string | null, env: Env): Promise<string> {
  if (!PROJECT.test(projectId) || !token || !TOKEN.test(token)) throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  const hash = await hashOwnerToken(token);
  const row = await env.DB.prepare(`SELECT 1 AS ok FROM project_owner_capabilities
    WHERE project_id=? AND token_hash=? AND revoked_at IS NULL`).bind(projectId, hash).first<{ok: number}>();
  if (row?.ok !== 1) throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  return hash;
}

async function version(env: Env, id: string): Promise<Version | null> {
  return env.DB.prepare(`SELECT id,title,status,submission_close_at,official_detail_url,captured_at
    FROM grant_call_versions WHERE id=?`).bind(id).first<Version>();
}
async function requirements(env: Env, id: string): Promise<Requirement[]> {
  const rows = await env.DB.prepare(`SELECT id,requirement_type,title,necessity,evidence_id
    FROM grant_requirements WHERE grant_call_version_id=? ORDER BY id`).bind(id).all<Requirement>();
  return rows.results ?? [];
}
function taskSeed(id: string, reqs: Requirement[], timestamp: string) {
  const items: Array<{ id: string; title: string; source: string; necessity: string; status: string; blocking: number; priority: number; reference: string | null; reason: string }> = reqs.map((r) => ({
    id: `tsk_${crypto.randomUUID().replaceAll("-", "")}`, title: r.title, source: "REQUIREMENT",
    necessity: r.necessity, status: r.necessity === "CONDITIONAL" ? "BLOCKED" : "TODO",
    blocking: r.necessity === "RECOMMENDED" ? 0 : 1,
    priority: r.necessity === "RECOMMENDED" ? 100 : 30,
    reference: r.id, reason: r.necessity === "CONDITIONAL" ? "CONDITION_UNKNOWN" : "REQUIREMENT",
  }));
  // No applicant facts/evaluation are available in this flow. These are explicit
  // non-completable blockers, never a fabricated eligibility or finance PASS.
  for (const [source, title, reason, priority] of [
    ["ELIGIBILITY", "Ověřte způsobilost projektu podle oficiálních podmínek", "ELIGIBILITY_UNKNOWN", 10],
    ["FINANCE", "Ověřte financování a vlastní zdroje projektu", "FINANCE_UNKNOWN", 20],
    ["REQUIREMENT", "Ověřte úplnost požadavků v oficiálním zdroji", "REQUIREMENTS_UNVERIFIED", 25],
  ] as const) {
    items.push({ id: `tsk_${crypto.randomUUID().replaceAll("-", "")}`, title, source,
      necessity: "REQUIRED", status: "BLOCKED", blocking: 1, priority,
      reference: null as string | null, reason });
  }
  return items.map((task) => ({ ...task, workspaceId: id, timestamp }));
}

export async function createWorkspace(projectId: string, token: string | null, grantCallId: string, env: Env) {
  const hash = await authorize(projectId, token, env);
  if (!grantCallId || grantCallId.length > 256) throw new ApiInputError("INVALID_GRANT_CALL");
  const existing = await env.DB.prepare(`SELECT id FROM application_workspaces WHERE project_id=? AND grant_call_id=?`)
    .bind(projectId, grantCallId).first<{id: string}>();
  if (existing) return readWorkspace(projectId, token, existing.id, env);
  const current = await env.DB.prepare(`SELECT current_version_id AS id FROM grant_calls WHERE id=?`)
    .bind(grantCallId).first<{id: string | null}>();
  if (!current?.id) throw new ApiInputError("GRANT_NOT_FOUND", 404);
  const reqs = await requirements(env, current.id);
  if (reqs.length > 200) throw new ApiInputError("WORKSPACE_REQUIREMENTS_TOO_MANY", 422);
  const id = `wsp_${crypto.randomUUID().replaceAll("-", "")}`;
  const timestamp = new Date().toISOString();
  const tasks = taskSeed(id, reqs, timestamp);
  const insert = env.DB.prepare(`INSERT OR IGNORE INTO application_workspaces
    (id,owner_user_id,project_id,grant_call_id,baseline_grant_version_id,status,created_at,updated_at)
    SELECT ?,p.owner_user_id,p.id,g.id,g.current_version_id,'PREPARING',?,?
    FROM projects p JOIN project_owner_capabilities c ON c.project_id=p.id
    JOIN grant_calls g ON g.id=? AND g.current_version_id=?
    WHERE p.id=? AND c.token_hash=? AND c.revoked_at IS NULL`)
    .bind(id, timestamp, timestamp, grantCallId, current.id, projectId, hash);
  const statements = [insert, ...tasks.map((task) => env.DB.prepare(`INSERT OR IGNORE INTO workspace_tasks
    (id,workspace_id,title,source,necessity,status,blocking,priority,reference_id,reason_code,created_at,updated_at)
    SELECT ?,w.id,?,?,?,?,?,?,?,?,?,? FROM application_workspaces w
    WHERE w.id=? AND w.project_id=? AND w.baseline_grant_version_id=?`)
    .bind(task.id, task.title, task.source, task.necessity, task.status, task.blocking,
      task.priority, task.reference, task.reason, timestamp, timestamp, id, projectId, current.id))];
  const result = await env.DB.batch(statements);
  if (result.some((r) => !r.success)) throw new Error("WORKSPACE_WRITE_FAILED");
  const workspace = await env.DB.prepare(`SELECT id FROM application_workspaces WHERE project_id=? AND grant_call_id=?`)
    .bind(projectId, grantCallId).first<{id: string}>();
  if (!workspace) throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  return readWorkspace(projectId, token, workspace.id, env);
}

export async function readWorkspace(projectId: string, token: string | null, workspaceId: string, env: Env) {
  await authorize(projectId, token, env);
  if (!WORKSPACE.test(workspaceId)) throw new ApiInputError("WORKSPACE_NOT_FOUND", 404);
  const workspace = await env.DB.prepare(`SELECT id,project_id,grant_call_id,baseline_grant_version_id,status
    FROM application_workspaces WHERE id=? AND project_id=?`).bind(workspaceId, projectId).first<Workspace>();
  if (!workspace) throw new ApiInputError("WORKSPACE_NOT_FOUND", 404);
  const currentId = await env.DB.prepare(`SELECT current_version_id AS id FROM grant_calls WHERE id=?`)
    .bind(workspace.grant_call_id).first<{id: string | null}>();
  const [base, current, oldReqs, newReqs, taskRows, sourceRows, evidenceRows] = await Promise.all([
    version(env, workspace.baseline_grant_version_id), version(env, currentId?.id ?? ""),
    requirements(env, workspace.baseline_grant_version_id), requirements(env, currentId?.id ?? ""),
    env.DB.prepare(`SELECT id,title,source,necessity,status,blocking,priority,reference_id,reason_code
      FROM workspace_tasks WHERE workspace_id=? ORDER BY priority,id`).bind(workspaceId).all<Task>(),
    env.DB.prepare(`SELECT sr.canonical_url, sr.last_seen_at FROM source_records sr
      WHERE sr.grant_call_id=? ORDER BY sr.last_seen_at DESC LIMIT 1`)
      .bind(workspace.grant_call_id).all<{canonical_url: string; last_seen_at: string}>(),
    env.DB.prepare(`SELECT id,field_path FROM field_evidence WHERE entity_id=?
      AND field_path IN ('/submission_close_at','/status') ORDER BY created_at DESC LIMIT 10`)
      .bind(currentId?.id ?? "").all<{id: string; field_path: string}>(),
  ]);
  if (!base || !current) throw new Error("WORKSPACE_VERSION_MISSING");
  if (!taskRows.success || !taskRows.results?.length) {
    throw new ApiInputError("WORKSPACE_UNAVAILABLE", 503);
  }
  const changed = base.id !== current.id;
  const changeRows = changed ? await env.DB.prepare(`SELECT field_path,old_value_json,new_value_json,evidence_id
    FROM change_events WHERE grant_call_id=? AND from_version_id=? AND to_version_id=?
    ORDER BY severity,id LIMIT 50`).bind(workspace.grant_call_id, base.id, current.id).all<ChangeRow>() : null;
  const detectedDiff = ((changeRows?.results ?? []) as ChangeRow[])
    .filter((row) => row.field_path && !(row.field_path.startsWith("requirements.") && displayChangeValue(row.new_value_json) === null))
    .map((row) => ({ field: row.field_path!, before: displayChangeValue(row.old_value_json),
      after: displayChangeValue(row.new_value_json), evidenceId: row.evidence_id }));
  const oldByKey = new Map(oldReqs.map((r) => [`${r.requirement_type}:${r.title}`, r]));
  const evidence = (evidenceRows.results ?? []) as Array<{id: string; field_path: string}>;
  // Absence from a newer normalized version is not proof of removal: a source
  // or parser may have omitted requirements. Never advertise a disappearance
  // as an authoritative change. Keep baseline tasks until source review.
  const fallbackDiff = [
    ...(base.submission_close_at !== current.submission_close_at ? [{ field: "submissionCloseAt", before: base.submission_close_at, after: current.submission_close_at, evidenceId: evidence.find((e) => e.field_path === "/submission_close_at")?.id ?? null }] : []),
    ...(base.status !== current.status ? [{ field: "status", before: base.status, after: current.status, evidenceId: evidence.find((e) => e.field_path === "/status")?.id ?? null }] : []),
    ...newReqs.filter((r) => !oldByKey.has(`${r.requirement_type}:${r.title}`)).map((r) => ({ field: "requirementAddedUnverified", before: null, after: r.title, evidenceId: r.evidence_id })),
    ...newReqs.filter((r) => {
      const old = oldByKey.get(`${r.requirement_type}:${r.title}`);
      return old && old.necessity !== r.necessity;
    }).map((r) => ({ field: "requirementNecessityUnverified", before: oldByKey.get(`${r.requirement_type}:${r.title}`)!.necessity, after: r.necessity, evidenceId: r.evidence_id })),
  ];
  const diff = detectedDiff.length ? detectedDiff : fallbackDiff;
  if (changed) {
    const result = await env.DB.prepare(`INSERT OR IGNORE INTO workspace_version_alerts(workspace_id,grant_call_version_id,created_at)
      SELECT ?,?,? WHERE EXISTS (SELECT 1 FROM application_workspaces WHERE id=? AND project_id=?)
      AND EXISTS (SELECT 1 FROM grant_calls WHERE id=? AND current_version_id=?)`)
      .bind(workspaceId, current.id, new Date().toISOString(), workspaceId, projectId, workspace.grant_call_id, current.id).run();
    if (!result.success) throw new Error("WORKSPACE_ALERT_WRITE_FAILED");
  }
  const alerts = await env.DB.prepare(`SELECT grant_call_version_id,created_at FROM workspace_version_alerts
    WHERE workspace_id=? ORDER BY created_at DESC LIMIT 20`).bind(workspaceId)
    .all<{grant_call_version_id: string; created_at: string}>();
  const tasks = (taskRows.results ?? []) as Task[];
  const active = tasks.filter((t) => t.status !== "NOT_APPLICABLE");
  const completed = active.filter((t) => t.status === "DONE");
  const blockingOpen = active.filter((t) => t.blocking === 1 && t.status !== "DONE");
  const next = changed ? { title: "Zkontrolujte změny podmínek výzvy vůči původní verzi", reasonCode: "VERSION_REVIEW" }
    : (blockingOpen[0] ?? active.find((t) => t.status !== "DONE") ?? null);
  return {
    workspace: { id: workspace.id, projectId, grantCallId: workspace.grant_call_id,
      baselineGrantVersionId: base.id, currentGrantVersionId: current.id, status: workspace.status },
    tasks, readiness: { state: changed || blockingOpen.some((t) => t.status === "BLOCKED") ? "BLOCKED" : blockingOpen.length ? "NEEDS_ACTION" : "READY",
      completedCount: completed.length, totalCount: active.length,
      completionPercent: active.length ? Math.round(100 * completed.length / active.length) : 100,
      blockingOpenCount: blockingOpen.length + (changed ? 1 : 0), nextAction: next },
    versionReview: { required: changed, diff, baselineCapturedAt: base.captured_at, currentCapturedAt: current.captured_at,
      sourceUrl: safeSourceUrl(current.official_detail_url) ?? safeSourceUrl(sourceRows.results?.[0]?.canonical_url),
      // A missing source observation is unknown, not the capture time of a version.
      sourceCheckedAt: sourceRows.results?.[0]?.last_seen_at ?? null,
      alerts: ((alerts.results ?? []) as Array<{grant_call_version_id: string; created_at: string}>).map((a) => ({ versionId: a.grant_call_version_id, createdAt: a.created_at })) },
  };
}

export async function listWorkspaces(projectId: string, token: string | null, env: Env) {
  await authorize(projectId, token, env);
  const rows = await env.DB.prepare(`SELECT id,grant_call_id,baseline_grant_version_id FROM application_workspaces
    WHERE project_id=? ORDER BY created_at DESC`).bind(projectId)
    .all<{id: string; grant_call_id: string; baseline_grant_version_id: string}>();
  return { workspaces: ((rows.results ?? []) as Array<{id: string; grant_call_id: string; baseline_grant_version_id: string}>).map((r) => ({ id: r.id, grantCallId: r.grant_call_id, baselineGrantVersionId: r.baseline_grant_version_id })) };
}

export async function updateWorkspaceTask(projectId: string, token: string | null, workspaceId: string, taskId: string, status: string, env: Env) {
  const hash = await authorize(projectId, token, env);
  if (!WORKSPACE.test(workspaceId) || !TASK.test(taskId)) throw new ApiInputError("TASK_NOT_FOUND", 404);
  if (!["TODO", "IN_PROGRESS", "DONE"].includes(status)) throw new ApiInputError("INVALID_TASK_STATUS");
  const result = await env.DB.prepare(`UPDATE workspace_tasks SET status=?,updated_at=?
    WHERE id=? AND workspace_id=? AND source='REQUIREMENT' AND reason_code='REQUIREMENT'
    AND EXISTS (SELECT 1 FROM application_workspaces w JOIN project_owner_capabilities c
      ON c.project_id=w.project_id WHERE w.id=? AND w.project_id=? AND c.token_hash=? AND c.revoked_at IS NULL)`)
    .bind(status, new Date().toISOString(), taskId, workspaceId, workspaceId, projectId, hash).run();
  if (!result.success) throw new Error("TASK_WRITE_FAILED");
  if (result.meta?.changes !== 1) throw new ApiInputError("TASK_NOT_FOUND", 404);
  return readWorkspace(projectId, token, workspaceId, env);
}
