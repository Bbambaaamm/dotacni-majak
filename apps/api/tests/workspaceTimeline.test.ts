import { describe, expect, it } from "vitest";

import type {
  D1DatabaseLike,
  D1PreparedStatementLike,
  D1ResultLike,
  Env,
} from "../src/env";
import { handleRequest } from "../src/index";
import { ApiInputError, hashOwnerToken } from "../src/projectAccess";
import {
  getWorkspaceTimeline,
  sortTimeline,
  workspaceTimelinePath,
} from "../src/workspaceTimeline";
import type { TimelineEntry, WorkspaceTimelineResponse } from "../src/workspaceTimeline";

/* ============================================================ *
 * Mock DB helpers
 * ============================================================ */

type DbMode = "first" | "all" | "run";
type DbResolver = (query: string, values: unknown[], mode: DbMode) => unknown;

const VALID_OWNER = "A".repeat(43);

function env(dbResult: unknown = { ok: 1 }, resolver?: DbResolver): Env {
  const defaultAll: D1ResultLike = { success: true, results: [] };
  const defaultRun: D1ResultLike = { success: true, meta: { changes: 1 }, results: [] };

  return {
    ENVIRONMENT: "local",
    DB: {
      prepare(query: string): D1PreparedStatementLike {
        let values: unknown[] = [];
        const statement: D1PreparedStatementLike = {
          bind(...next: unknown[]): D1PreparedStatementLike { values = next; return statement; },
          async first<T = unknown>(): Promise<T | null> {
            if (resolver) return resolver(query, values, "first") as T | null;
            return dbResult as T | null;
          },
          async all<T = unknown>(): Promise<D1ResultLike & { results?: T[] }> {
            if (resolver) {
              const v = resolver(query, values, "all");
              if (v && typeof v === "object" && "success" in v) {
                return v as D1ResultLike & { results?: T[] };
              }
            }
            return defaultAll as D1ResultLike & { results: T[] };
          },
          async run<T = unknown>(): Promise<D1ResultLike & { results?: T[] }> {
            if (resolver) {
              const v = resolver(query, values, "run");
              if (v && typeof v === "object" && "success" in v) {
                return v as D1ResultLike & { results?: T[] };
              }
              return defaultRun as D1ResultLike & { results?: T[] };
            }
            return defaultRun;
          },
        };
        return statement;
      },
      async batch(statements: D1PreparedStatementLike[]): Promise<D1ResultLike[]> {
        if (!resolver) return Promise.resolve(statements.map(() => defaultRun));
        return Promise.all(statements.map((s) => s.run() as Promise<D1ResultLike>));
      },
    },
    RAW: { head: async () => null },
    SEARCH: { describe: async () => ({}) },
  } as unknown as Env;
}

/* --- row types --- */
interface WsRow { id: string; project_id: string; grant_call_id: string; owner_user_id: string | null; status: string; updated_at: string; }
interface CapRow { project_id: string; token_hash: string; revoked_at: string | null; }
interface VerRow { version_id: string; current_version_id: string; }
interface DlRow { id: string; deadline_type: string; starts_at: string | null; ends_at: string | null; timezone: string | null; description: string | null; evidence_id: string | null; }
interface TkRow { id: string; title: string; source: string; status: string; due_at: string; reference_id: string | null; ws_id: string; }

function makeData(overrides: Partial<{
  workspace: WsRow | null;
  capability: boolean;
  version: VerRow | null;
  deadlines: DlRow[];
  tasks: TkRow[];
}> = {}): DbResolver {
  const ws = overrides.workspace ?? {
    id: "wrk_test123", project_id: "prj_test123", grant_call_id: "gc_test123",
    owner_user_id: "anon:test", status: "READY_TO_SUBMIT", updated_at: "2026-01-01T00:00:00Z",
  };
  const cap = overrides.capability !== undefined ? overrides.capability : true;
  const ver = overrides.version ?? { version_id: "v_test123", current_version_id: "v_test123" };
  const dls = overrides.deadlines ?? [];
  const tks = overrides.tasks ?? [];

  return (query, values, mode) => {
    if (mode === "first" && query.includes("application_workspaces")) {
      if (!ws || ws.id !== values[0]) return null;
      return { ...ws };
    }
    if (mode === "first" && query.includes("project_owner_capabilities")) {
      return cap ? { ok: 1 } : null;
    }
    if (mode === "first" && query.includes("grant_call_versions")) {
      return ver;
    }
    if (mode === "all" && query.includes("grant_deadlines")) {
      return { success: true, results: dls };
    }
    if (mode === "all" && query.includes("workspace_tasks")) {
      const rows = tks.filter((t) => t.ws_id === String(values[0]) && t.status !== "DONE" && t.status !== "NOT_APPLICABLE");
      return { success: true, results: rows };
    }
    if (mode === "run") {
      return { success: true, meta: { changes: 1 } };
    }
    return null;
  };
}

/* ============================================================ *
 * Path parser
 * ============================================================ */

describe("workspaceTimelinePath", () => {
  it("matches valid workspace timeline paths", () => {
    expect(workspaceTimelinePath("/workspaces/wrk_test/timeline")).toBe("wrk_test");
  });
  it("returns null for non-timeline workspace paths", () => {
    expect(workspaceTimelinePath("/workspaces/wrk_test")).toBeNull();
    expect(workspaceTimelinePath("/workspaces/wrk_test/watch")).toBeNull();
  });
  it("returns null for paths with extra segments", () => {
    expect(workspaceTimelinePath("/workspaces/wrk_test/timeline/extra")).toBeNull();
  });
  it("returns null for project paths", () => {
    expect(workspaceTimelinePath("/projects/prj_test/timeline")).toBeNull();
  });
  it("rejects overly long IDs", () => {
    expect(workspaceTimelinePath("/workspaces/" + "A".repeat(300) + "/timeline")).toBeNull();
  });
});

/* ============================================================ *
 * Sort
 * ============================================================ */

function mkEntry(overrides: Partial<TimelineEntry>): TimelineEntry {
  type R = Required<TimelineEntry>;
  return {
    id: "x",
    type: "USER_TASK",
    date: "2026-01-01T00:00:00Z",
    endAt: null,
    timezone: null,
    title: "T",
    description: null,
    source: "USER",
    workspaceTaskId: null,
    deadlineId: null,
    workspaceTaskReferenceId: null,
    ...overrides,
  } as TimelineEntry;
}

describe("sortTimeline", () => {
  it("sorts chronologically ascending", () => {
    const sorted = sortTimeline([
      mkEntry({ id: "b", date: "2026-10-01T00:00:00Z" }),
      mkEntry({ id: "a", date: "2026-09-01T00:00:00Z" }),
      mkEntry({ id: "c", date: "2026-09-15T00:00:00Z" }),
    ]);
    expect(sorted.map((e) => e.id)).toEqual(["a", "c", "b"]);
  });

  it("ties: OFFICIAL before SYSTEM_TASK before USER_TASK", () => {
    const d = "2026-09-01T00:00:00Z";
    const sorted = sortTimeline([
      mkEntry({ id: "u", type: "USER_TASK", date: d }),
      mkEntry({ id: "s", type: "SYSTEM_TASK", date: d }),
      mkEntry({ id: "o", type: "OFFICIAL", date: d }),
    ]);
    expect(sorted.map((e) => e.type)).toEqual(["OFFICIAL", "SYSTEM_TASK", "USER_TASK"]);
  });

  it("ties: by id (deterministic)", () => {
    const d = "2026-09-01T00:00:00Z";
    const sorted = sortTimeline([
      mkEntry({ id: "z", type: "USER_TASK", date: d }),
      mkEntry({ id: "a", type: "USER_TASK", date: d }),
    ]);
    expect(sorted.map((e) => e.id)).toEqual(["a", "z"]);
  });

  it("does not mutate input", () => {
    const input = [mkEntry({ id: "b", date: "2026-10-01T00:00:00Z" }), mkEntry({ id: "a", date: "2026-09-01T00:00:00Z" })];
    sortTimeline(input);
    expect(input.map((e) => e.id)).toEqual(["b", "a"]);
  });
});


function mkTask(id: string, source: string, status: string, dueAt: string): TkRow {
  return { id, title: `Task ${id}`, source, status, due_at: dueAt, reference_id: null, ws_id: "wrk_test123" };
}

/* ============================================================ *
 * getWorkspaceTimeline unit tests
 * ============================================================ */

describe("getWorkspaceTimeline", () => {
  const deadlines: DlRow[] = [
    { id: "dl1", deadline_type: "APPLICATION_CLOSE", starts_at: null, ends_at: "2026-10-15T17:00:00Z", timezone: "Europe/Prague", description: "Close apps", evidence_id: null },
    { id: "dl2", deadline_type: "PROJECT_START", starts_at: "2026-11-01T00:00:00Z", ends_at: null, timezone: "Europe/Prague", description: null, evidence_id: null },
  ];
  const tasks: TkRow[] = [
    { id: "t1", title: "Gather evidence", source: "SYSTEM", status: "TODO", due_at: "2026-10-01T00:00:00Z", reference_id: "dl1", ws_id: "wrk_test123" },
    { id: "t2", title: "Call accountant", source: "USER", status: "IN_PROGRESS", due_at: "2026-09-20T00:00:00Z", reference_id: null, ws_id: "wrk_test123" },
  ];

  it("merges official deadlines + tasks, sorted, with dedup", async () => {
    const envObj = env(null, makeData({ deadlines, tasks }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    expect(result.workspaceId).toBe("wrk_test123");
    expect(result.grantCallId).toBe("gc_test123");
    expect(result.entries).toHaveLength(3);
    // t2 (Sep 20) → merged t1+dl1 (Oct 1 — task ref, date from task) → dl2 (Nov 1)
    expect(result.entries[0].id).toBe("task:t2");
    expect(result.entries[0].type).toBe("USER_TASK");
    expect(result.entries[1].id).toBe("deadline:dl1");
    expect(result.entries[1].title).toBe("Gather evidence"); // task title wins
    expect(result.entries[1].workspaceTaskId).toBe("t1");
    expect(result.entries[2].id).toBe("deadline:dl2");
  });

  it("returns empty entries when no deadlines or tasks", async () => {
    const envObj = env(null, makeData({ deadlines: [], tasks: [] }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    expect(result.entries).toHaveLength(0);
  });

  it("labels official deadlines correctly", async () => {
    const envObj = env(null, makeData({ deadlines, tasks: [] }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    const dl = result.entries.find((e) => e.deadlineId === "dl1");
    expect(dl).toBeDefined();
    expect(dl!.type).toBe("OFFICIAL");
    expect(dl!.source).toBe("OFFICIAL");
    expect(dl!.timezone).toBe("Europe/Prague");
  });

  it("labels user tasks as USER_TASK / USER", async () => {
    const envObj = env(null, makeData({ deadlines: [], tasks }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    const userTask = result.entries.find((e) => e.type === "USER_TASK");
    expect(userTask).toBeDefined();
    expect(userTask!.source).toBe("USER");
  });

  it("labels system tasks as SYSTEM_TASK / SYSTEM", async () => {
    const envObj = env(null, makeData({ deadlines: [], tasks }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    const sysTask = result.entries.find((e) => e.type === "SYSTEM_TASK");
    expect(sysTask).toBeDefined();
    expect(sysTask!.source).toBe("SYSTEM");
  });

  it("excludes completed / not-applicable tasks", async () => {
    const envObj = env(null, makeData({
      deadlines: [],
      tasks: [
        mkTask("done", "USER", "DONE", "2026-10-01T00:00:00Z"),
        mkTask("na", "SYSTEM", "NOT_APPLICABLE", "2026-09-01T00:00:00Z"),
        mkTask("active", "USER", "TODO", "2026-08-01T00:00:00Z"),
      ],
    }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    expect(result.entries).toHaveLength(1);
    expect(result.entries[0].id).toBe("task:active");
  });

  it("throws WORKSPACE_NOT_FOUND for unknown workspace", async () => {
    const envObj = env(null, makeData({ workspace: null }));
    try {
      await getWorkspaceTimeline("wrk_unknown", VALID_OWNER, envObj);
      expect.fail("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiInputError);
      expect((e as ApiInputError).code).toBe("WORKSPACE_NOT_FOUND");
      expect((e as ApiInputError).status).toBe(404);
    }
  });

  it("throws OWNER_CAPABILITY_INVALID for malformed token", async () => {
    const envObj = env(null, makeData());
    await expect(getWorkspaceTimeline("wrk_test123", "short", envObj)).rejects.toThrow(ApiInputError);
  });

  it("throws OWNER_CAPABILITY_INVALID when capability does not match", async () => {
    const envObj = env(null, makeData({ capability: false }));
    try {
      await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
      expect.fail("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiInputError);
      expect((e as ApiInputError).code).toBe("OWNER_CAPABILITY_INVALID");
    }
  });

  it("includes fetchedAt ISO timestamp", async () => {
    const envObj = env(null, makeData());
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    expect(result.fetchedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("uses deadline effective date (ends_at for windows)", async () => {
    const envObj = env(null, makeData({
      deadlines: [{ id: "dl1", deadline_type: "APPLICATION_OPEN", starts_at: "2026-09-01T09:00:00Z", ends_at: "2026-10-15T17:00:00Z", timezone: null, description: null, evidence_id: null }],
      tasks: [],
    }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    expect(result.entries[0].date).toBe("2026-10-15T17:00:00Z");
    expect(result.entries[0].endAt).toBe("2026-10-15T17:00:00Z");
  });

  it("falls back to starts_at when ends_at is null", async () => {
    const envObj = env(null, makeData({
      deadlines: [{ id: "dl1", deadline_type: "PROJECT_START", starts_at: "2026-11-01T00:00:00Z", ends_at: null, timezone: null, description: null, evidence_id: null }],
      tasks: [],
    }));
    const result = await getWorkspaceTimeline("wrk_test123", VALID_OWNER, envObj);
    expect(result.entries[0].date).toBe("2026-11-01T00:00:00Z");
    expect(result.entries[0].endAt).toBeNull();
  });
});
