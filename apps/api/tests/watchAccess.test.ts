import { describe, expect, it } from "vitest";

import type {
  D1DatabaseLike,
  D1PreparedStatementLike,
  D1ResultLike,
  Env,
} from "../src/env";
import {
  deleteProjectWatch,
  enableProjectWatch,
  getProjectWatch,
  parseWatchEnabled,
  setProjectWatchEnabled,
} from "../src/watchAccess";
import { ApiInputError } from "../src/projectAccess";

interface WatchState {
  id: string;
  projectId: string;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

function fakeEnv(authorized = true): Env {
  let watch: WatchState | null = null;

  const db: D1DatabaseLike = {
    prepare(query: string): D1PreparedStatementLike {
      let values: unknown[] = [];
      const statement: D1PreparedStatementLike = {
        bind(...next: unknown[]) {
          values = next;
          return statement;
        },
        async first<T = unknown>() {
          if (query.includes("FROM project_owner_capabilities")) {
            return (authorized ? { ok: 1 } : null) as T | null;
          }
          if (query.includes("FROM watches")) {
            if (!watch) return null;
            return {
              id: watch.id,
              project_id: watch.projectId,
              enabled: watch.enabled ? 1 : 0,
              minimum_match_band: "POSSIBLE",
              created_at: watch.createdAt,
              updated_at: watch.updatedAt,
            } as T;
          }
          return null;
        },
        async all<T = unknown>() {
          return { success: true, results: [] as T[] };
        },
        async run<T = unknown>() {
          if (query.includes("INSERT OR IGNORE INTO watches")) {
            if (!watch) {
              watch = {
                id: String(values[0]),
                projectId: String(values[1]),
                enabled: true,
                createdAt: String(values[2]),
                updatedAt: String(values[3]),
              };
              return { success: true, meta: { changes: 1 }, results: [] as T[] };
            }
            return { success: true, meta: { changes: 0 }, results: [] as T[] };
          }
          if (query.includes("UPDATE watches") && query.includes("SET enabled = 1")) {
            if (watch) {
              watch.enabled = true;
              watch.updatedAt = String(values[0]);
            }
            return {
              success: true,
              meta: { changes: watch ? 1 : 0 },
              results: [] as T[],
            };
          }
          if (query.includes("UPDATE watches") && query.includes("SET enabled = ?")) {
            if (watch) {
              watch.enabled = values[0] === 1;
              watch.updatedAt = String(values[1]);
            }
            return {
              success: true,
              meta: { changes: watch ? 1 : 0 },
              results: [] as T[],
            };
          }
          if (query.includes("DELETE FROM watches")) {
            watch = null;
            return { success: true, meta: { changes: 1 }, results: [] as T[] };
          }
          return { success: true, meta: { changes: 1 }, results: [] as T[] };
        },
      };
      return statement;
    },
    async batch(statements: D1PreparedStatementLike[]): Promise<D1ResultLike[]> {
      return Promise.all(statements.map((statement) => statement.run()));
    },
  };

  return {
    ENVIRONMENT: "local",
    DB: db,
    RAW: { async head() { return null; } },
    SEARCH: { async describe() { return {}; } },
  };
}

const PROJECT = "prj_" + "a".repeat(32);
const OWNER = "A".repeat(43);

describe("project watch access", () => {
  it("creates idempotently, pauses, resumes and deletes", async () => {
    const env = fakeEnv();

    const first = await enableProjectWatch(PROJECT, OWNER, env);
    const second = await enableProjectWatch(PROJECT, OWNER, env);
    expect(first.id).toBe(second.id);
    expect(second.enabled).toBe(true);

    const paused = await setProjectWatchEnabled(PROJECT, OWNER, false, env);
    expect(paused.enabled).toBe(false);

    const resumed = await setProjectWatchEnabled(PROJECT, OWNER, true, env);
    expect(resumed.enabled).toBe(true);

    expect(await getProjectWatch(PROJECT, OWNER, env)).not.toBeNull();
    await deleteProjectWatch(PROJECT, OWNER, env);
    expect(await getProjectWatch(PROJECT, OWNER, env)).toBeNull();

    // Authorized delete is intentionally idempotent.
    await deleteProjectWatch(PROJECT, OWNER, env);
  });

  it("collapses invalid ownership to 404", async () => {
    const env = fakeEnv(false);
    await expect(enableProjectWatch(PROJECT, OWNER, env)).rejects.toMatchObject({
      code: "OWNER_CAPABILITY_INVALID",
      status: 404,
    } satisfies Partial<ApiInputError>);
  });

  it("validates PATCH body strictly", async () => {
    await expect(
      parseWatchEnabled(new Request("https://example.test", {
        method: "PATCH",
        body: JSON.stringify({ enabled: true }),
      })),
    ).resolves.toBe(true);

    await expect(
      parseWatchEnabled(new Request("https://example.test", {
        method: "PATCH",
        body: JSON.stringify({ enabled: "yes" }),
      })),
    ).rejects.toMatchObject({ code: "INVALID_WATCH_ENABLED" });
  });
});
