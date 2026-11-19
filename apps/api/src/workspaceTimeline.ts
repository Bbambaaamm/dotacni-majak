import type { Env } from "./env";
import { ApiInputError, hashOwnerToken } from "./projectAccess";

const OWNER_TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;

/**
 * AbortError is thrown when the request is cancelled (e.g. client disconnect).
 * It is NOT an ApiInputError, so it surfaces as 503 fail-closed, and it
 * preserves the semantic that UNKNOWN != FAIL — a cancellation is neither
 * a user error nor a source-truth failure.
 */
class AbortError extends Error {
  readonly name = "AbortError";
  constructor(message: string) {
    super(message);
  }
}

/* ========================================================================= *
 * Types
 * ========================================================================= */

export type TimelineEntryType = "OFFICIAL" | "USER_TASK" | "SYSTEM_TASK";

/** A single deadline / task on the unified timeline. */
export interface TimelineEntry {
  /** Stable unique ID (prefixed: `deadline:` or `task:`). */
  id: string;
  /** OFFICIAL = from grant_deadlines (source truth); USER_TASK / SYSTEM_TASK = from workspace_tasks. */
  type: TimelineEntryType;
  /** Effective deadline instant (ISO 8601). Point deadlines use starts_at or ends_at. */
  date: string;
  /** End of a time-window deadline (ISO 8601) or null for point deadlines. */
  endAt: string | null;
  /** Timezone of the deadline source (grant_deadlines have timezone; user tasks do not). */
  timezone: string | null;
  /** Human-readable label. */
  title: string;
  /** Optional longer description (typically from grant_deadline.description). */
  description: string | null;
  /** Provenance: OFFICIAL (grant), USER (user-created task), or SYSTEM (eligibility/finance/requirement rule). */
  source: "OFFICIAL" | "USER" | "SYSTEM";
  /** The workspace_task this entry derives from, if any. */
  workspaceTaskId: string | null;
  /** The grant_deadline this entry derives from, if any. */
  deadlineId: string | null;
  /** When a task references a deadline, this holds the deadline_id (for dedup). */
  workspaceTaskReferenceId: string | null;
}

/** Unified response returned by `GET /workspaces/{id}/timeline`. */
export interface WorkspaceTimelineResponse {
  workspaceId: string;
  grantCallId: string;
  timezone: string | null; // user/workspace preferred timezone (NULL until UX sets it)
  entries: TimelineEntry[];
  fetchedAt: string;
}

/* Internal row types (snake_case from D1) */
interface DeadlineRow {
  id: string;
  deadline_type: string;
  starts_at: string | null;
  ends_at: string | null;
  timezone: string | null;
  description: string | null;
  evidence_id: string | null;
}
interface TaskRow {
  id: string;
  title: string;
  source: string;
  status: string;
  due_at: string;
  reference_id: string | null;
}

/* ========================================================================= *
 * Path parser
 * ========================================================================= */

/**
 * Match `/workspaces/{workspaceId}/timeline`.
 * Workspace IDs are opaque URL-safe tokens validated by DB lookup.
 */
export function workspaceTimelinePath(pathname: string): string | null {
  const m = pathname.match(/^\/workspaces\/([^/]+)\/timeline$/);
  if (!m || !m[1]) return null;
  try {
    const raw = decodeURIComponent(m[1]);
    if (!raw || raw.length > 256) return null;
    if (!/^[A-Za-z0-9_\-:]{1,256}$/.test(raw)) return null;
    return raw;
  } catch {
    return null;
  }
}

/* ========================================================================= *
 * Helpers
 * ========================================================================= */

/** Effective deadline instant: prefer endsAt, fall back to startsAt. */
function deadlineEffectiveDate(startsAt: string | null, endsAt: string | null): string | null {
  if (endsAt !== null) return endsAt;
  if (startsAt !== null) return startsAt;
  return null;
}

function deadlineTypeLabel(t: string): string {
  const labels: Record<string, string> = {
    APPLICATION_OPEN: "Application opens",
    APPLICATION_CLOSE: "Application closes",
    PROJECT_START: "Project start",
    PROJECT_FINISH: "Project finish",
    DOCUMENT_COMPLETION: "Document completion",
    SUSTAINABILITY_END: "Sustainability end",
    OTHER: "Other deadline",
  };
  return labels[t] ?? t;
}

function deadlineToEntry(
  id: string, type: string, startsAt: string | null, endsAt: string | null,
  timezone: string | null, description: string | null,
): TimelineEntry {
  return {
    id: `deadline:${id}`,
    type: "OFFICIAL",
    date: deadlineEffectiveDate(startsAt, endsAt) ?? "",
    endAt: endsAt,
    timezone,
    title: deadlineTypeLabel(type),
    description,
    source: "OFFICIAL",
    workspaceTaskId: null,
    deadlineId: id,
    workspaceTaskReferenceId: null,
  };
}

/**
 * Sort chronologically (ascending). Ties broken by:
 * 1. Type rank: OFFICIAL < SYSTEM_TASK < USER_TASK
 * 2. ID (stable, deterministic)
 */
export function sortTimeline(entries: TimelineEntry[]): TimelineEntry[] {
  const typeRank: Record<TimelineEntryType, number> = {
    OFFICIAL: 0,
    SYSTEM_TASK: 1,
    USER_TASK: 2,
  };
  return [...entries].sort((a, b) => {
    const da = Date.parse(a.date);
    const db = Date.parse(b.date);
    if (da !== db) return da - db;
    const ra = typeRank[a.type] ?? 99;
    const rb = typeRank[b.type] ?? 99;
    if (ra !== rb) return ra - rb;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

/* ========================================================================= *
 * Main entry point
 * ========================================================================= */

/**
 * Fetch and merge official grant deadlines + user/system workspace tasks
 * with due dates into a unified, sorted timeline.
 *
 * Authorization: bearer *** must match the workspace's project owner
 * capability (hashOwnerToken + project_owner_capabilities lookup).
 *
 * Fail-closed semantics:
 *   - Malformed token: 404 OWNER_CAPABILITY_INVALID (non-disclosing)
 *   - Unknown workspace: 404 WORKSPACE_NOT_FOUND (non-disclosing)
 *   - Invalid capability: 404 OWNER_CAPABILITY_INVALID (non-disclosing)
 *   - DB error after successful auth: 503 (via route-level try/catch)
 */
export async function getWorkspaceTimeline(
  workspaceId: string,
  ownerToken: string,
  env: Env,
  signal?: AbortSignal,
): Promise<WorkspaceTimelineResponse> {
  if (signal?.aborted) {
    throw new AbortError("TIMELINE_ABORTED");
  }

  // --- validate owner token format ---
  if (!OWNER_TOKEN_RE.test(ownerToken)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }

  // --- workspace lookup (active workspaces only) ---
  const workspace = await env.DB.prepare(`
    SELECT id, project_id, grant_call_id, owner_user_id, status, updated_at
    FROM application_workspaces
    WHERE id = ? AND status IN ('PREPARING','READY_TO_SUBMIT','SUBMITTED','ARCHIVED')
    LIMIT 1
  `).bind(workspaceId).first<{
    id: string; project_id: string; grant_call_id: string;
    owner_user_id: string | null; status: string; updated_at: string;
  }>();

  if (!workspace) {
    throw new ApiInputError("WORKSPACE_NOT_FOUND", 404);
  }

  // --- owner capability verification (non-disclosing 404 on mismatch) ---
  const ownerHash = await hashOwnerToken(ownerToken);
  const capability = await env.DB.prepare(`
    SELECT 1 AS ok FROM project_owner_capabilities
    WHERE project_id = ? AND token_hash = ? AND revoked_at IS NULL
    LIMIT 1
  `).bind(workspace.project_id, ownerHash).first<{ ok: number }>();

  if (capability?.ok !== 1) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }

  // --- official deadlines (from grant_call's current version) ---
  const versionRow = await env.DB.prepare(`
    SELECT v.id AS version_id, gc.current_version_id
    FROM grant_calls gc
    JOIN grant_call_versions v ON v.id = gc.current_version_id
    WHERE gc.id = ?
    LIMIT 1
  `).bind(workspace.grant_call_id).first<{ version_id: string; current_version_id: string }>();

  let deadlineRows: DeadlineRow[] = [];
  if (versionRow) {
    const raw = await env.DB.prepare(`
      SELECT id, deadline_type, starts_at, ends_at, timezone, description, evidence_id
      FROM grant_deadlines
      WHERE grant_call_version_id = ?
      ORDER BY COALESCE(ends_at, starts_at, '9999') ASC, id ASC
      LIMIT 100
    `).bind(versionRow.version_id).all<DeadlineRow>();
    deadlineRows = raw?.results ?? [];
  }

  // --- workspace tasks with due dates (active only) ---
  const taskRaw = await env.DB.prepare(`
    SELECT id, title, source, status, due_at, reference_id
    FROM workspace_tasks
    WHERE workspace_id = ?
      AND due_at IS NOT NULL
      AND status IN ('TODO','IN_PROGRESS','BLOCKED')
    ORDER BY due_at ASC, id ASC
    LIMIT 200
  `).bind(workspaceId).all<TaskRow>();
  const tasks = taskRaw?.results ?? [];

  // --- merge: deadlines first, then tasks ---
  // If a task references a deadline via reference_id, the task takes precedence
  // (richer info: task title, source) but keeps the deadline date.
  const merged = new Map<string, TimelineEntry>();
  for (const row of deadlineRows) {
    const entry = deadlineToEntry(
      row.id, row.deadline_type, row.starts_at, row.ends_at, row.timezone, row.description,
    );
    merged.set(entry.id, entry);
  }
  for (const row of tasks) {
    const taskEntry: TimelineEntry = {
      id: `task:${row.id}`,
      type: row.source === "USER" ? "USER_TASK" : "SYSTEM_TASK",
      date: row.due_at,
      endAt: null,
      timezone: null,
      title: row.title,
      description: null,
      source: row.source === "USER" ? "USER" : "SYSTEM",
      workspaceTaskId: row.id,
      deadlineId: row.reference_id,
      workspaceTaskReferenceId: row.reference_id,
    };
    if (row.reference_id) {
      const deadlineKey = `deadline:${row.reference_id}`;
      const existing = merged.get(deadlineKey);
      if (existing) {
        // Overwrite deadline entry with task's title/source
        merged.set(existing.id, {
          ...existing,
          title: row.title,
          source: "OFFICIAL",
          type: "OFFICIAL",
          workspaceTaskId: row.id,
        });
        continue;
      }
    }
    merged.set(taskEntry.id, taskEntry);
  }

  const entries = sortTimeline(Array.from(merged.values()));

  if (signal?.aborted) {
    throw new AbortError("TIMELINE_ABORTED");
  }

  return {
    workspaceId: workspace.id,
    grantCallId: workspace.grant_call_id,
    timezone: null,
    entries,
    fetchedAt: new Date().toISOString(),
  };
}
